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
            "label": "Xem kênh Official",
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
            "label": "Trend nhảy",
            "actionType": "reply_text",
            "targetReportCode": "TREND_DANCE_REPORT",
            "actionGroup": "trend",
            "callbackPayload": encode_callback_payload(
                {
                    "action": "reply_text",
                    "target_report_code": "TREND_DANCE_REPORT",
                    "message": "Trend nhảy đang được cập nhật. Tôi sẽ mở nút này ngay khi category data sẵn sàng.",
                    "source_report_code": report_code,
                    "group_name": group_name,
                    "generated_at": generated_at,
                }
            ),
        },
        {
            "label": "Trend tình huống",
            "actionType": "reply_text",
            "targetReportCode": "TREND_SITUATION_REPORT",
            "actionGroup": "trend",
            "callbackPayload": encode_callback_payload(
                {
                    "action": "reply_text",
                    "target_report_code": "TREND_SITUATION_REPORT",
                    "message": "Trend tình huống đang được cập nhật. Tôi sẽ mở nút này ngay khi category data sẵn sàng.",
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
    grouped: list[dict[str, Any]] = []
    campaign_actions = [item for item in actions if item.get("actionGroup") == "campaign_official"]
    trend_actions = [item for item in actions if item.get("actionGroup") == "trend"]

    if campaign_actions:
        grouped.append(
            {
                "title": "Mở rộng báo cáo",
                "description": "Nhấn nút để nhận thêm dữ liệu Campaign hoặc kênh Official qua tin nhắn riêng.",
                "actions": campaign_actions[:5],
            }
        )
    if trend_actions:
        grouped.append(
            {
                "title": "Theo dõi trend",
                "description": "Nhấn nút để xem thêm dữ liệu trend nhảy và trend tình huống qua tin nhắn riêng.",
                "actions": trend_actions[:5],
            }
        )
    return grouped


def encode_callback_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_callback_payload(payload: str) -> dict[str, Any]:
    return json.loads(payload)
