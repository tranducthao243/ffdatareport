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
            "actionGroup": "campaign_official",
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
            "actionGroup": "campaign_official",
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
        {
            "label": "Trend nhay",
            "actionType": "reply_text",
            "targetReportCode": "TREND_DANCE_REPORT",
            "actionGroup": "trend",
            "callbackPayload": encode_callback_payload(
                {
                    "action": "reply_text",
                    "target_report_code": "TREND_DANCE_REPORT",
                    "message": "Trend nhay dang duoc cap nhat. Toi se mo nut nay ngay khi category data san sang.",
                    "source_report_code": report_code,
                    "group_name": group_name,
                    "generated_at": generated_at,
                }
            ),
        },
        {
            "label": "Trend tinh huong",
            "actionType": "reply_text",
            "targetReportCode": "TREND_SITUATION_REPORT",
            "actionGroup": "trend",
            "callbackPayload": encode_callback_payload(
                {
                    "action": "reply_text",
                    "target_report_code": "TREND_SITUATION_REPORT",
                    "message": "Trend tinh huong dang duoc cap nhat. Toi se mo nut nay ngay khi category data san sang.",
                    "source_report_code": report_code,
                    "group_name": group_name,
                    "generated_at": generated_at,
                }
            ),
        },
    ]


def build_interactive_groups(package: dict[str, Any]) -> list[dict[str, Any]]:
    actions = list(package.get("interactiveActions") or [])
    if not actions:
        return []
    return [
        {
            "title": "Mo rong bao cao",
            "description": (
                "Nhan nut de nhan them du lieu Campaign, kenh Official, "
                "trend nhay hoac trend tinh huong qua tin nhan private."
            ),
            "actions": actions[:5],
        }
    ]


def encode_callback_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_callback_payload(payload: str) -> dict[str, Any]:
    return json.loads(payload)
