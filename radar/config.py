from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def load_json(relative_path: str):
    with (ROOT / relative_path).open(encoding="utf-8") as handle:
        return json.load(handle)


def db_path() -> Path:
    value = os.getenv("RADAR_DB_PATH", "data/radar.db")
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def ai_settings(overrides: dict | None = None) -> dict:
    settings = {
        "base_url": os.getenv("RADAR_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        "api_key": os.getenv("RADAR_AI_API_KEY", ""),
        "model": os.getenv("RADAR_AI_MODEL", "gpt-4.1-mini"),
        "mode": os.getenv("RADAR_AI_MODE", "auto"),
        "timeout": int(os.getenv("RADAR_AI_TIMEOUT_SECONDS", "90")),
    }
    settings.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return settings
