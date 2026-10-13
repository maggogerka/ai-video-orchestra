from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import websocket

from video_orchestra.errors import ComfyClientError


class WebSocketLike(Protocol):
    def recv(self) -> str | bytes: ...

    def close(self) -> None: ...

    def settimeout(self, timeout: float) -> None: ...


class ComfyClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 1800,
        *,
        client_id: str | None = None,
        http_client: httpx.Client | None = None,
        ws_factory: Callable[..., WebSocketLike] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = client_id or str(uuid.uuid4())
        self._owns_http_client = http_client is None
        self.http = http_client or httpx.Client(
            base_url=f"{self.base_url}/", timeout=httpx.Timeout(timeout)
        )
        self.ws_factory = ws_factory or websocket.create_connection

    def close(self) -> None:
        if self._owns_http_client:
            self.http.close()

    def __enter__(self) -> ComfyClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        try:
            response = self.http.post(
                "prompt", json={"prompt": workflow, "client_id": self.client_id}
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:2000].strip()
            message = f"ComfyUI отклонил workflow (HTTP {exc.response.status_code})"
            if detail:
                message = f"{message}: {detail}"
            raise ComfyClientError(message) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ComfyClientError(f"ComfyUI отклонил workflow: {exc}") from exc
        prompt_id = payload.get("prompt_id") if isinstance(payload, dict) else None
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ComfyClientError("ответ POST /prompt не содержит prompt_id")
        return prompt_id

    def _websocket_url(self) -> str:
        parts = urlsplit(self.base_url)
        scheme = "wss" if parts.scheme == "https" else "ws"
        path = f"{parts.path.rstrip('/')}/ws"
        query = urlencode({"clientId": self.client_id})
        return urlunsplit((scheme, parts.netloc, path, query, ""))

    def wait_for_completion(
        self,
        prompt_id: str,
        on_generating: Callable[[], None] | None = None,
    ) -> None:
        deadline = time.monotonic() + self.timeout
        generating_reported = False
        try:
            ws = self.ws_factory(self._websocket_url(), timeout=min(30.0, self.timeout))
        except Exception as exc:
            raise ComfyClientError(f"не удалось подключиться к WebSocket ComfyUI: {exc}") from exc

        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ComfyClientError(
                        f"таймаут {self.timeout:g} сек. при ожидании prompt_id {prompt_id}"
                    )
                ws.settimeout(min(30.0, remaining))
                try:
                    message = ws.recv()
                except (websocket.WebSocketTimeoutException, TimeoutError):
                    if self._history_has_output(prompt_id):
                        return
                    continue
                except Exception as exc:
                    message = f"ошибка WebSocket при ожидании генерации: {exc}"
                    raise ComfyClientError(message) from exc

                if isinstance(message, bytes):
                    continue
                try:
                    event = json.loads(message)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(event, dict):
                    continue
                data = event.get("data")
                if not isinstance(data, dict) or data.get("prompt_id") != prompt_id:
                    continue

                event_type = event.get("type")
                if event_type in {"execution_start", "executing", "progress"}:
                    if not generating_reported and on_generating is not None:
                        on_generating()
                        generating_reported = True
                if event_type == "executing" and data.get("node") is None:
                    return
                if event_type == "execution_success":
                    return
                if event_type in {"execution_error", "execution_interrupted"}:
                    detail = data.get("exception_message") or data.get("node_id") or event_type
                    raise ComfyClientError(f"ComfyUI сообщил об ошибке генерации: {detail}")
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        try:
            response = self.http.get(f"history/{prompt_id}")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            message = f"не удалось получить историю prompt_id {prompt_id}: {exc}"
            raise ComfyClientError(message) from exc
        if not isinstance(payload, dict):
            raise ComfyClientError("GET /history вернул неожиданный формат")
        entry = payload.get(prompt_id)
        if not isinstance(entry, dict):
            raise ComfyClientError(f"в истории ComfyUI нет prompt_id {prompt_id}")
        return entry

    def _history_has_output(self, prompt_id: str) -> bool:
        try:
            history = self.get_history(prompt_id)
        except ComfyClientError:
            return False
        return isinstance(history.get("outputs"), dict) and bool(history["outputs"])

    @staticmethod
    def find_output(history: dict[str, Any]) -> dict[str, str]:
        outputs = history.get("outputs")
        if not isinstance(outputs, dict):
            raise ComfyClientError("история не содержит outputs")

        candidates: list[dict[str, Any]] = []
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for collection in ("videos", "files", "gifs", "images"):
                items = node_output.get(collection)
                if isinstance(items, list):
                    candidates.extend(item for item in items if isinstance(item, dict))

        if not candidates:
            raise ComfyClientError("в outputs не найден файл в videos, files, gifs или images")

        video_extensions = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif"}
        selected = next(
            (
                item
                for item in candidates
                if Path(str(item.get("filename", ""))).suffix.casefold() in video_extensions
            ),
            candidates[0],
        )
        filename = selected.get("filename")
        if not isinstance(filename, str) or not filename:
            raise ComfyClientError("описание результата не содержит filename")
        return {
            "filename": filename,
            "subfolder": str(selected.get("subfolder", "")),
            "type": str(selected.get("type", "output")),
        }

    def download_output(self, output: dict[str, str], destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(f"{destination.suffix}.part")
        try:
            with self.http.stream("GET", "view", params=output) as response:
                response.raise_for_status()
                with partial.open("wb") as target:
                    for chunk in response.iter_bytes():
                        target.write(chunk)
            if partial.stat().st_size == 0:
                raise ComfyClientError("ComfyUI вернул пустой видеофайл")
            partial.replace(destination)
        except (httpx.HTTPError, OSError) as exc:
            raise ComfyClientError(f"не удалось сохранить видео в {destination}: {exc}") from exc
