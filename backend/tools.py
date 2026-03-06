from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def _resolve_path(filename: str) -> Path:
    target_path = Path(filename)

    if not target_path.is_absolute():
        target_path = WORKSPACE_ROOT / target_path

    return target_path


def write_file_tool(filename: str, content: str) -> str:
    target_path = _resolve_path(filename)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    return f"Wrote file: {target_path}"


def read_file_tool(filename: str) -> str:
    target_path = _resolve_path(filename)

    if not target_path.exists():
        return f"File not found: {target_path}"

    return target_path.read_text(encoding="utf-8")
