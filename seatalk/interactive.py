from __future__ import annotations

import json
from typing import Any


def build_interactive_actions(package: dict[str, Any]) -> list[dict[str, Any]]:
    report_code = str(package.get("reportCode") or "").strip()
    if report_code != "SO1":
        return []

    group_name = str(package.get("groupName") or "").strip()
    generated_at = str(package.get("generatedAt") or "").strip()

    return [
        {
            "label": "Xem campaign",
            "actionType": "open_report",
            "targetReportCode": "TOPD_REPORT",
            "callbackPayload": encode_callback_payload(
                {
                    "action": "open_report",
                    "target_report_code": "TOPD_REPORT",
                    "source_report_code": report_code,
                    "group_name": group_name,
                    "generated_at": generated_at,
                }
            ),
        },
        {
            "label": "Xem kenh Official",
            "actionType": "open_report",
            "targetReportCode": "TOPF_REPORT",
            "callbackPayload": encode_callback_payload(
                {
                    "action": "open_report",
                    "target_report_code": "TOPF_REPORT",
                    "source_report_code": report_code,
                    "group_name": group_name,
                    "generated_at": generated_at,
                }
            ),
        },
    ]


def encode_callback_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_callback_payload(payload: str) -> dict[str, Any]:
    return json.loads(payload)
