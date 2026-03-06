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
    "timeout": 240.0,
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
    ensure_storage_dirs()

    if not SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)

    try:
        stored_settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(DEFAULT_SETTINGS)

    if not isinstance(stored_settings, dict):
        return dict(DEFAULT_SETTINGS)

    merged_settings = dict(DEFAULT_SETTINGS)
    merged_settings.update(stored_settings)
    return merged_settings


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged_settings = dict(DEFAULT_SETTINGS)
    merged_settings.update(settings)
    ensure_storage_dirs()
    SETTINGS_FILE.write_text(json.dumps(merged_settings, indent=2), encoding="utf-8")
    return merged_settings
