from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from video_orchestra.errors import WorkflowFormatError, WorkflowNodeError

Workflow = dict[str, dict[str, Any]]


@dataclass(frozen=True)
class NodeRef:
    node_id: str
    node: dict[str, Any]

    @property
    def class_type(self) -> str:
        return str(self.node.get("class_type", ""))

    @property
    def title(self) -> str:
        meta = self.node.get("_meta")
        return str(meta.get("title", "")) if isinstance(meta, dict) else ""

    @property
    def inputs(self) -> dict[str, Any]:
        inputs = self.node.get("inputs")
        return inputs if isinstance(inputs, dict) else {}


@dataclass(frozen=True)
class RequiredNodes:
    positive: NodeRef
    negative: NodeRef
    sampler: NodeRef
    latent: NodeRef
    create_video: NodeRef
    save_video: NodeRef


def validate_api_workflow(data: Any) -> Workflow:
    if not isinstance(data, dict) or not data:
        raise WorkflowFormatError("workflow должен быть непустым JSON-объектом")

    for node_id, node in data.items():
        if not isinstance(node_id, str) or not isinstance(node, dict):
            raise WorkflowFormatError("API workflow должен быть объектом из узлов по node_id")
        if not isinstance(node.get("class_type"), str) or not isinstance(node.get("inputs"), dict):
            raise WorkflowFormatError(
                f"узел {node_id!r} не содержит строковый class_type и объект inputs; "
                "экспортируйте workflow через Save (API Format)"
            )
    return data


def load_api_workflow(path: Path) -> Workflow:
    try:
        with path.open(encoding="utf-8") as source:
            data = json.load(source)
    except FileNotFoundError:
        raise WorkflowFormatError(f"файл workflow не найден: {path}") from None
    except json.JSONDecodeError as exc:
        raise WorkflowFormatError(
            f"workflow содержит некорректный JSON: строка {exc.lineno}, столбец {exc.colno}"
        ) from exc
    except OSError as exc:
        raise WorkflowFormatError(f"не удалось прочитать workflow: {exc}") from exc
    return validate_api_workflow(data)


class WorkflowAdapter:
    def __init__(self, workflow: Workflow) -> None:
        validate_api_workflow(workflow)
        self.workflow = copy.deepcopy(workflow)

    @classmethod
    def from_file(cls, path: Path) -> WorkflowAdapter:
        return cls(load_api_workflow(path))

    def nodes(self) -> list[NodeRef]:
        return [NodeRef(str(node_id), node) for node_id, node in self.workflow.items()]

    def _find_one(self, label: str, predicate: Callable[[NodeRef], bool]) -> NodeRef:
        matches = [node for node in self.nodes() if predicate(node)]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            reason = "не найден"
        else:
            ids = ", ".join(node.node_id for node in matches)
            reason = f"найден неоднозначно (node_id: {ids})"
        raise WorkflowNodeError(
            f"узел {label} {reason}. Выполните inspect-workflow и проверьте class_type/_meta.title."
        )

    def find_required_nodes(self) -> RequiredNodes:
        def title_contains(node: NodeRef, word: str) -> bool:
            return node.class_type == "CLIPTextEncode" and word in node.title.casefold()

        positive = self._find_one(
            "CLIPTextEncode positive",
            lambda node: title_contains(node, "positive")
            and "negative" not in node.title.casefold(),
        )
        negative = self._find_one(
            "CLIPTextEncode negative", lambda node: title_contains(node, "negative")
        )
        sampler = self._find_one("KSampler", lambda node: node.class_type == "KSampler")
        latent = self._find_one(
            "Wan22ImageToVideoLatent",
            lambda node: node.class_type == "Wan22ImageToVideoLatent",
        )
        create_video = self._find_one(
            "CreateVideo", lambda node: node.class_type == "CreateVideo"
        )
        save_video = self._find_one("SaveVideo", lambda node: node.class_type == "SaveVideo")
        return RequiredNodes(positive, negative, sampler, latent, create_video, save_video)

    @staticmethod
    def _set_required(node: NodeRef, key: str, value: Any) -> None:
        if key not in node.inputs:
            raise WorkflowNodeError(
                f"у узла {node.class_type} (node_id: {node.node_id}) нет input {key!r}. "
                "Выполните inspect-workflow и проверьте версию узла."
            )
        node.inputs[key] = value

    def apply(
        self,
        *,
        prompt: str,
        negative: str,
        width: int,
        height: int,
        frames: int,
        fps: float,
        seed: int,
        steps: int,
        cfg: float,
        filename_prefix: str,
    ) -> Workflow:
        required = self.find_required_nodes()
        self._set_required(required.positive, "text", prompt)
        self._set_required(required.negative, "text", negative)
        self._set_required(required.sampler, "seed", seed)
        self._set_required(required.sampler, "steps", steps)
        self._set_required(required.sampler, "cfg", cfg)
        self._set_required(required.latent, "width", width)
        self._set_required(required.latent, "height", height)
        self._set_required(required.latent, "length", frames)

        fps_updated = False
        for node in (required.create_video, required.save_video):
            for key in ("frame_rate", "fps"):
                if key in node.inputs:
                    node.inputs[key] = fps
                    fps_updated = True
        if not fps_updated:
            raise WorkflowNodeError(
                "у узлов CreateVideo/SaveVideo нет input 'frame_rate' или 'fps'. "
                "Выполните inspect-workflow и проверьте версию узлов."
            )

        self._set_required(required.save_video, "filename_prefix", filename_prefix)
        return copy.deepcopy(self.workflow)


SPECIAL_CLASSES = {
    "KSampler",
    "Wan22ImageToVideoLatent",
    "CreateVideo",
    "SaveVideo",
}


def is_special_node(node: NodeRef) -> bool:
    if node.class_type in SPECIAL_CLASSES:
        return True
    title = node.title.casefold()
    return node.class_type == "CLIPTextEncode" and (
        "positive" in title or "negative" in title
    )
