from __future__ import annotations

import json
from typing import Any

from datasocial.exceptions import DatasocialError

from .interactive import decode_callback_payload


class SeatalkCallbackError(DatasocialError):
    """Callback payload or event handling error."""


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def extract_sender_employee_code(event: dict[str, Any]) -> str:
    return _first_non_empty(
        event.get("employee_code"),
        event.get("sender", {}).get("employee_code"),
        event.get("operator", {}).get("employee_code"),
        event.get("employee", {}).get("employee_code"),
    )


def extract_click_value(event: dict[str, Any]) -> str:
    return _first_non_empty(
        event.get("value")
        or event.get("action", {}).get("value"),
        event.get("button", {}).get("value"),
        event.get("callback_data"),
    )


def extract_group_id(event: dict[str, Any]) -> str:
    return _first_non_empty(
        event.get("group_id"),
        event.get("chat_id"),
        event.get("conversation_id"),
        event.get("group", {}).get("group_id"),
        event.get("group", {}).get("id"),
        event.get("chat", {}).get("group_id"),
        event.get("chat", {}).get("chat_id"),
        event.get("conversation", {}).get("group_id"),
        event.get("conversation", {}).get("id"),
        event.get("message", {}).get("group_id"),
        event.get("message", {}).get("chat_id"),
    )


def extract_message_id(event: dict[str, Any]) -> str:
    return _first_non_empty(
        event.get("message_id"),
        event.get("message", {}).get("message_id"),
        event.get("action", {}).get("message_id"),
        event.get("context", {}).get("message_id"),
    )


def extract_thread_id(event: dict[str, Any]) -> str:
    return _first_non_empty(
        event.get("thread_id"),
        event.get("message", {}).get("thread_id"),
        event.get("action", {}).get("thread_id"),
        event.get("context", {}).get("thread_id"),
    )


def extract_quoted_message_id(event: dict[str, Any]) -> str:
    return _first_non_empty(
        event.get("quoted_message_id"),
        event.get("message", {}).get("quoted_message_id"),
        event.get("action", {}).get("quoted_message_id"),
        event.get("context", {}).get("quoted_message_id"),
    )


def build_callback_context(event: dict[str, Any]) -> dict[str, str]:
    return {
        "employee_code": extract_sender_employee_code(event),
        "group_id": extract_group_id(event),
        "message_id": extract_message_id(event),
        "thread_id": extract_thread_id(event),
        "quoted_message_id": extract_quoted_message_id(event),
        "click_value": extract_click_value(event),
    }


def parse_click_payload(raw_value: str) -> dict[str, Any]:
    if not raw_value:
        raise SeatalkCallbackError("Interactive click payload is empty.")
    try:
        payload = decode_callback_payload(raw_value)
    except json.JSONDecodeError:
        payload = {"action": raw_value}
    if not isinstance(payload, dict):
        raise SeatalkCallbackError("Interactive click payload is not an object.")
    return payload
