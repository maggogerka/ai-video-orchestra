from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    comfy_url: str = "http://127.0.0.1:8188"
    comfy_timeout_sec: float = 1800
    comfy_workflow: Path = Path("workflows/wan22_5b_t2v_api.json")
    runs_dir: Path = Path("runs")

    @field_validator("comfy_url")
    @classmethod
    def normalize_comfy_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("COMFY_URL должен начинаться с http:// или https://")
        return value

    @field_validator("comfy_timeout_sec")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("COMFY_TIMEOUT_SEC должен быть больше нуля")
        return value
