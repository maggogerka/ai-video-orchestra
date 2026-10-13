from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class JobRun:
    def __init__(self, runs_dir: Path, job_id: str | None = None) -> None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.job_id = job_id or f"{timestamp}-{uuid.uuid4().hex[:8]}"
        self.directory = runs_dir / self.job_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.prompt_id: str | None = None
        self.logger = logging.getLogger(f"video_orchestra.job.{self.job_id}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        handler = logging.FileHandler(self.directory / "run.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.logger.addHandler(handler)
        self.write_status("created", stage="created")

    def _write_json(self, name: str, payload: dict[str, Any]) -> None:
        destination = self.directory / name
        temporary = destination.with_suffix(f"{destination.suffix}.tmp")
        with temporary.open("w", encoding="utf-8") as target:
            json.dump(payload, target, ensure_ascii=False, indent=2)
            target.write("\n")
        temporary.replace(destination)

    def write_request(self, request: dict[str, Any]) -> None:
        self._write_json("request.json", request)
        self.logger.info("Request saved")

    def write_workflow(self, workflow: dict[str, Any]) -> None:
        self._write_json("workflow_submitted.json", workflow)
        self.logger.info("Submitted workflow snapshot saved")

    def write_status(self, status: str, *, stage: str, **details: Any) -> None:
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "status": status,
            "stage": stage,
            "updated_at": utc_now(),
        }
        if self.prompt_id is not None:
            payload["prompt_id"] = self.prompt_id
        payload.update(details)
        self._write_json("status.json", payload)
        self.logger.info("Status: %s (stage: %s)", status, stage)

    def fail(self, *, stage: str, error: Exception) -> None:
        self.logger.exception("Job failed at stage %s", stage, exc_info=error)
        self.write_status(
            "failed",
            stage=stage,
            error_type=type(error).__name__,
            error_message=str(error),
        )

    @property
    def video_path(self) -> Path:
        return self.directory / "scene.mp4"
