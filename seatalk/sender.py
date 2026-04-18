from __future__ import annotations

from typing import Any

from .auth import build_seatalk_client
from .payloads import build_text_payload


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
        client = build_seatalk_client(app_id=app_id, app_secret=app_secret, group_id=group_id)
        client.send_text(build_text_payload(package["renderedText"]))
        results.append(
            {
                "groupName": package["groupName"],
                "reportCode": package["reportCode"],
                "status": "sent",
                "groupId": group_id,
            }
        )
    return results
