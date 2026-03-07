import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent / "data"
SCRIPTS_DIR = DATA_DIR / "scripts"
AGENTS_DIR = DATA_DIR / "agents"
SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "provider": "ollama",
    "model": "qwen3:4b",
    "timeout": 300.0,
    "llm_server": "http://192.168.129.11:11434",
}


def ensure_storage_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)


def save_record(directory: Path, record_id: str, record: dict[str, Any]) -> None:
    ensure_storage_dirs()
    target_path = directory / f"{record_id}.json"
    target_path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def load_records(directory: Path) -> list[dict[str, Any]]:
    ensure_storage_dirs()
    records: list[dict[str, Any]] = []

    for path in directory.glob("*.json"):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue

    return sorted(
        records,
        key=lambda record: str(record.get("updatedAt", "")),
        reverse=True,
    )


def load_record(directory: Path, record_id: str) -> dict[str, Any] | None:
    ensure_storage_dirs()
    target_path = directory / f"{record_id}.json"

    if not target_path.exists():
        return None

    return json.loads(target_path.read_text(encoding="utf-8"))


def load_settings() -> dict[str, Any]:
    """Deprecated: returns default settings. Use get_session_settings from tools for session-scoped settings."""
    return dict(DEFAULT_SETTINGS)
