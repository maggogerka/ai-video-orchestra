from __future__ import annotations

import copy
from typing import Any

import pytest


@pytest.fixture
def api_workflow() -> dict[str, dict[str, Any]]:
    workflow = {
        "text-pos": {
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIPTextEncode Positive"},
            "inputs": {"text": "old positive", "clip": ["loader", 0]},
        },
        "text-neg": {
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIPTextEncode Negative"},
            "inputs": {"text": "old negative", "clip": ["loader", 0]},
        },
        "sampler": {
            "class_type": "KSampler",
            "_meta": {"title": "KSampler"},
            "inputs": {"seed": 1, "steps": 10, "cfg": 1.5},
        },
        "latent": {
            "class_type": "Wan22ImageToVideoLatent",
            "_meta": {"title": "Wan latent"},
            "inputs": {"width": 1, "height": 1, "length": 1},
        },
        "create": {
            "class_type": "CreateVideo",
            "_meta": {"title": "Create Video"},
            "inputs": {"images": ["decode", 0], "fps": 1},
        },
        "save": {
            "class_type": "SaveVideo",
            "_meta": {"title": "Save Video"},
            "inputs": {"video": ["create", 0], "filename_prefix": "old"},
        },
        "loader": {
            "class_type": "CLIPLoader",
            "_meta": {"title": "Loader"},
            "inputs": {"clip_name": "model.safetensors"},
        },
    }
    return copy.deepcopy(workflow)
