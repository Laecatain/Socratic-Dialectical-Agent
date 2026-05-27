from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYTHON_SUFFIXES = {".py", ".pyi"}
EXCLUDED_PARTS = {
    ".venv",
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


def normalize_path(raw: str) -> Path:
    if raw.startswith("/") and len(raw) > 2 and raw[2] == "/" and raw[1].isalpha():
        raw = f"{raw[1].upper()}:{raw[2:]}"
    return Path(raw).resolve()


def edited_file(payload: dict[str, object]) -> Path | None:
    tool_input = payload.get("tool_input")
    tool_response = payload.get("tool_response")
    raw = ""
    if isinstance(tool_input, dict):
        raw = str(tool_input.get("file_path") or "")
    if not raw and isinstance(tool_response, dict):
        raw = str(tool_response.get("filePath") or "")
    if not raw:
        return None
    return normalize_path(raw)


def is_project_python_file(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return path.suffix in PYTHON_SUFFIXES and not any(
        part in EXCLUDED_PARTS for part in relative.parts
    )


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    root = Path(__file__).resolve().parent.parent
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    path = edited_file(payload)
    if path is None or not is_project_python_file(path, root):
        return 0
    command_by_mode = {
        "check": [sys.executable, "-m", "ruff", "check", "--fix", str(path)],
        "format-check": [sys.executable, "-m", "ruff", "format", "--check", str(path)],
    }
    command = command_by_mode.get(mode)
    if command is None:
        return 2
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
