from __future__ import annotations

from typing import Any

from .auth import build_seatalk_client
from .payloads import build_interactive_payload, build_text_payload


def send_report_packages(
    packages: list[dict[str, Any]],
    *,
    app_id: str,
    app_secret: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for package in packages:
        group_id = package.get("resolvedGroupId", "")
        if not group_id:
            results.append(
                {
                    "groupName": package["groupName"],
                    "reportCode": package["reportCode"],
                    "status": "skipped",
                    "reason": "missing_group_id",
                }
            )
            continue
        try:
            client = build_seatalk_client(app_id=app_id, app_secret=app_secret, group_id=group_id)
            client.send_text(build_text_payload(package["renderedText"]))
            interactive_status = "not_applicable"
            interactive_actions = package.get("interactiveActions") or []
            if interactive_actions:
                interactive_payload = build_interactive_payload(
                    title=str(package.get("title") or package.get("reportCode") or "Report"),
                    description="Chọn dữ liệu muốn xem thêm.",
                    actions=interactive_actions,
                )
                try:
                    client.send_interactive(interactive_payload)
                    interactive_status = "sent"
                except Exception as exc:
                    interactive_status = "failed"
                    results.append(
                        {
                            "groupName": package["groupName"],
                            "reportCode": package["reportCode"],
                            "status": "interactive_failed",
                            "groupId": group_id,
                            "reason": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
            results.append(
                {
                    "groupName": package["groupName"],
                    "reportCode": package["reportCode"],
                    "status": "sent",
                    "groupId": group_id,
                    "interactiveStatus": interactive_status,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "groupName": package["groupName"],
                    "reportCode": package["reportCode"],
                    "status": "failed",
                    "groupId": group_id,
                    "reason": type(exc).__name__,
                    "message": str(exc),
                }
            )
    return results
