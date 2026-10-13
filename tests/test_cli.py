from __future__ import annotations

import json

from typer.testing import CliRunner

from video_orchestra.cli import app

runner = CliRunner()


def test_inspect_workflow_prints_every_node(tmp_path, api_workflow):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(json.dumps(api_workflow), encoding="utf-8")

    result = runner.invoke(app, ["inspect-workflow", str(workflow_path)])

    assert result.exit_code == 0
    for node_id in api_workflow:
        assert node_id in result.stdout
    assert "KSampler" in result.stdout
    assert "Wan22ImageToVideoLatent" in result.stdout


def test_generate_failure_creates_diagnostic_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COMFY_WORKFLOW", "missing-workflow.json")
    monkeypatch.setenv("RUNS_DIR", "runs")

    result = runner.invoke(app, ["generate", "--prompt", "test prompt"])

    assert result.exit_code == 1
    job_directories = list((tmp_path / "runs").iterdir())
    assert len(job_directories) == 1
    status = json.loads((job_directories[0] / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["stage"] == "load_workflow"
    assert status["error_type"] == "WorkflowFormatError"
    assert (job_directories[0] / "request.json").is_file()
    assert (job_directories[0] / "run.log").is_file()
