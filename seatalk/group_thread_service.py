from __future__ import annotations


def split_csv_env(*values: str) -> list[str]:
    items: list[str] = []
    for raw in values:
        for token in str(raw or "").replace(";", ",").split(","):
            value = token.strip()
            if value and value not in items:
                items.append(value)
    return items


def is_allowed_ctv_group(runtime: dict[str, object], callback_context: dict[str, str]) -> bool:
    group_id = str(callback_context.get("group_id") or "").strip()
    return bool(group_id and group_id in set(runtime.get("ctv_group_ids") or []))
