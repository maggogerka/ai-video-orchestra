from __future__ import annotations

import copy
import json

import pytest

from video_orchestra.errors import WorkflowFormatError, WorkflowNodeError
from video_orchestra.workflow import WorkflowAdapter, load_api_workflow


def test_adapter_changes_copy_without_mutating_source(api_workflow):
    source = copy.deepcopy(api_workflow)
    adapter = WorkflowAdapter(api_workflow)

    result = adapter.apply(
        prompt="new positive",
        negative="new negative",
        width=480,
        height=832,
        frames=81,
        fps=16,
        seed=42,
        steps=20,
        cfg=5,
        filename_prefix="unique-job",
    )

    assert api_workflow == source
    assert result["text-pos"]["inputs"]["text"] == "new positive"
    assert result["text-neg"]["inputs"]["text"] == "new negative"
    assert result["sampler"]["inputs"] == {"seed": 42, "steps": 20, "cfg": 5}
    assert result["latent"]["inputs"] == {"width": 480, "height": 832, "length": 81}
    assert result["create"]["inputs"]["fps"] == 16
    assert result["save"]["inputs"]["filename_prefix"] == "unique-job"


def test_adapter_rejects_ambiguous_nodes(api_workflow):
    api_workflow["another-positive"] = copy.deepcopy(api_workflow["text-pos"])

    with pytest.raises(WorkflowNodeError, match="неоднозначно"):
        WorkflowAdapter(api_workflow).find_required_nodes()


def test_load_rejects_ui_workflow(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")

    with pytest.raises(WorkflowFormatError, match="API workflow"):
        load_api_workflow(path)
