from __future__ import annotations

from app.health import normalize_command_text


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


def derive_group_thread_id(callback_context: dict[str, str]) -> str:
    thread_id = str(callback_context.get("thread_id") or "").strip()
    if thread_id:
        return thread_id
    return str(callback_context.get("message_id") or "").strip()


def message_addresses_bot(message_text: str, aliases: list[str]) -> bool:
    normalized = normalize_command_text(message_text)
    if not normalized:
        return False
    return any(alias and alias in normalized for alias in aliases)


def strip_group_bot_aliases(message_text: str, aliases: list[str]) -> str:
    normalized = normalize_command_text(message_text)
    if not normalized:
        return ""
    cleaned = normalized
    for alias in aliases:
        if alias:
            cleaned = cleaned.replace(alias, " ")
            if alias.startswith("@"):
                cleaned = cleaned.replace(alias.lstrip("@"), " ")
    cleaned = cleaned.replace("@", " ")
    return " ".join(cleaned.split()).strip()
