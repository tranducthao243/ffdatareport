from __future__ import annotations

import json
from typing import Any


def build_interactive_actions(package: dict[str, Any]) -> list[dict[str, Any]]:
    report_code = str(package.get("reportCode") or "").strip()
    if report_code != "SO1":
        return []

    return [
        {
            "label": "Xem Campaign",
            "actionType": "open_report",
            "targetReportCode": "TOPD_REPORT",
            "actionGroup": "campaign_official",
            "callbackPayload": encode_callback_payload(
                {
                    "action": "open_report",
                    "target_report_code": "TOPD_REPORT",
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
                }
            ),
        },
        {
            "label": "Trend nhảy",
            "actionType": "open_report",
            "targetReportCode": "TOPG_REPORT",
            "actionGroup": "trend",
            "callbackPayload": encode_callback_payload(
                {
                    "action": "open_report",
                    "target_report_code": "TOPG_REPORT",
                }
            ),
        },
        {
            "label": "Roblox Content",
            "actionType": "open_report",
            "targetReportCode": "TOPH_REPORT",
            "actionGroup": "trend",
            "callbackPayload": encode_callback_payload(
                {
                    "action": "open_report",
                    "target_report_code": "TOPH_REPORT",
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
                "description": "Nhấn nút để nhận thêm dữ liệu Campaign hoặc kênh Official qua tin nhắn riêng.",
                "actions": campaign_actions[:5],
            }
        )
    if trend_actions:
        grouped.append(
            {
                "description": "Nhấn nút để xem thêm dữ liệu Trend Nhảy và Roblox Content qua tin nhắn riêng.",
                "actions": trend_actions[:5],
            }
        )
    return grouped


def build_superadmin_control_actions() -> list[dict[str, Any]]:
    return [
        {
            "label": "Fetch",
            "actionType": "trigger_workflow",
            "workflow": "ffvn-daily-fetch.yml",
            "callbackPayload": encode_callback_payload(
                {
                    "action": "trigger_workflow",
                    "workflow": "ffvn-daily-fetch.yml",
                }
            ),
        },
        {
            "label": "Send",
            "actionType": "trigger_workflow",
            "workflow": "ffvn-daily-send.yml",
            "callbackPayload": encode_callback_payload(
                {
                    "action": "trigger_workflow",
                    "workflow": "ffvn-daily-send.yml",
                }
            ),
        },
    ]


def build_superadmin_control_payload() -> dict[str, Any]:
    return build_interactive_payload(
        title="Điều Khiển Trung Tâm",
        description="Bấm để chạy workflow quét dữ liệu hoặc gửi báo cáo.",
        actions=build_superadmin_control_actions(),
    )


def encode_callback_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_callback_payload(payload: str) -> dict[str, Any]:
    return json.loads(payload)
