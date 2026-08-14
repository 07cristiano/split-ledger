"""Small local configuration helpers; secrets remain outside version control."""

from __future__ import annotations

import os
from pathlib import Path


def load_local_env(env_path: str | Path) -> None:
    """Load simple KEY=VALUE entries without overriding real environment variables."""
    path = Path(env_path)
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)
