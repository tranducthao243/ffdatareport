from __future__ import annotations

import json
from typing import Any

from datasocial.exceptions import DatasocialError

from .interactive import decode_callback_payload


class SeatalkCallbackError(DatasocialError):
    """Callback payload or event handling error."""


def extract_sender_employee_code(event: dict[str, Any]) -> str:
    return str(event.get("employee_code") or "").strip()


def extract_click_value(event: dict[str, Any]) -> str:
    return str(
        event.get("value")
        or event.get("action", {}).get("value")
        or event.get("button", {}).get("value")
        or event.get("callback_data")
        or ""
    ).strip()


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
