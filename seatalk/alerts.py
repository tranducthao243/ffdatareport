from __future__ import annotations

import logging
from typing import Any

from .auth import build_seatalk_client


LOGGER = logging.getLogger("seatalk.alerts")


def send_superadmin_alerts(
    *,
    app_id: str,
    app_secret: str,
    superadmins: list[dict[str, Any]],
    title: str,
    body: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    message = f"**{title}**\n{body}".strip()
    for admin in superadmins:
        employee_code = str(admin.get("employee_code") or "").strip()
        if not employee_code:
            LOGGER.warning(
                "Skipping superadmin alert because employee_code is missing | email=%s | seatalk_user_id=%s",
                admin.get("email") or "-",
                admin.get("seatalk_user_id") or "-",
            )
            results.append({"status": "skipped", "reason": "missing_employee_code", "admin": admin})
            continue
        try:
            build_seatalk_client(
                app_id=app_id,
                app_secret=app_secret,
                employee_code=employee_code,
            ).send_text(message)
            results.append({"status": "sent", "employee_code": employee_code})
        except Exception as exc:
            LOGGER.exception("Superadmin alert failed | employee_code=%s", employee_code)
            results.append(
                {
                    "status": "failed",
                    "employee_code": employee_code,
                    "reason": type(exc).__name__,
                    "message": str(exc),
                }
            )
    return results
