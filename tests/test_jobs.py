from __future__ import annotations

import json

from video_orchestra.jobs import JobRun


def test_failed_job_records_error_and_prompt_id(tmp_path):
    job = JobRun(tmp_path, job_id="test-job")
    job.prompt_id = "prompt-42"

    try:
        raise RuntimeError("generation failed")
    except RuntimeError as exc:
        job.fail(stage="generating", error=exc)

    status = json.loads((job.directory / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["stage"] == "generating"
    assert status["error_type"] == "RuntimeError"
    assert status["error_message"] == "generation failed"
    assert status["prompt_id"] == "prompt-42"
    assert (job.directory / "run.log").is_file()
