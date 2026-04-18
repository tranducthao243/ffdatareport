from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_group_target(group: dict[str, Any]) -> str:
    if group.get("group_id"):
        return str(group["group_id"]).strip()
    env_key = str(group.get("group_id_env") or "").strip()
    if env_key:
        return os.getenv(env_key, "").strip()
    return ""
