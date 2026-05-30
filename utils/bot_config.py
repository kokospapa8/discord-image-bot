"""Global bot configuration stored at /app/data/config.json."""
from __future__ import annotations

import json
from pathlib import Path

_FILE = Path("/app/data/config.json")


def load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save(data: dict) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_mode() -> str:
    """Returns 'T' or 'F' (default 'F')."""
    return load().get("advice_mode", "F")


def set_mode(mode: str) -> None:
    data = load()
    data["advice_mode"] = mode.upper()
    save(data)
