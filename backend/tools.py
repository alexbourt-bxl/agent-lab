from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = WORKSPACE_ROOT / "results"


def _normalize_results_path(target_path: Path) -> Path:
    if target_path.suffix == "":
        target_path = target_path.with_suffix(".md")
    elif target_path.suffix == ".txt":
        target_path = target_path.with_suffix(".md")

    return target_path


def _resolve_path(filename: str) -> Path:
    target_path = Path(filename)

    if not target_path.is_absolute():
        if target_path.parts and target_path.parts[0] == "results":
            target_path = WORKSPACE_ROOT / target_path
        else:
            target_path = RESULTS_ROOT / target_path

    target_path = _normalize_results_path(target_path)

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
