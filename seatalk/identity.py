from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class UnifiedUser:
    role: str
    employee_code: str = ""
    email: str = ""
    seatalk_user_id: str = ""
    gmail: str = ""
    name: str = ""


def _split_env_values(*raw_values: str) -> list[str]:
    values: list[str] = []
    for raw in raw_values:
        for token in str(raw or "").replace(";", ",").split(","):
            value = token.strip()
            if value and value not in values:
                values.append(value)
    return values


def load_user_directory(path: Path) -> list[UnifiedUser]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_users = payload.get("users") if isinstance(payload, dict) else payload
    if not isinstance(raw_users, list):
        return []
    users: list[UnifiedUser] = []
    for item in raw_users:
        if not isinstance(item, dict):
            continue
        users.append(
            UnifiedUser(
                role=str(item.get("role") or "admin").strip().lower(),
                employee_code=str(item.get("employee_code") or "").strip(),
                email=str(item.get("email") or "").strip().lower(),
                seatalk_user_id=str(item.get("seatalk_user_id") or item.get("seatalk_id") or "").strip(),
                gmail=str(item.get("gmail") or "").strip().lower(),
                name=str(item.get("name") or "").strip(),
            )
        )
    return users


def load_env_role_directory() -> list[UnifiedUser]:
    users: list[UnifiedUser] = []

    for employee_code in _split_env_values(
        os.getenv("SEATALK_SUPERADMIN_EMPLOYEE_CODES", ""),
        os.getenv("SEATALK_SUPERADMIN_EMPLOYEE_CODE", ""),
    ):
        users.append(UnifiedUser(role="superadmin", employee_code=employee_code))
    for email in _split_env_values(
        os.getenv("SEATALK_SUPERADMIN_EMAILS", ""),
        os.getenv("SEATALK_SUPERADMIN_EMAIL", ""),
    ):
        users.append(UnifiedUser(role="superadmin", email=email.lower()))
    for seatalk_user_id in _split_env_values(
        os.getenv("SEATALK_SUPERADMIN_SEATALK_IDS", ""),
        os.getenv("SEATALK_SUPERADMIN_SEATALK_ID", ""),
    ):
        users.append(UnifiedUser(role="superadmin", seatalk_user_id=seatalk_user_id))

    for employee_code in _split_env_values(
        os.getenv("SEATALK_ADMIN_EMPLOYEE_CODES", ""),
        os.getenv("SEATALK_ADMIN_EMPLOYEE_CODE", ""),
    ):
        users.append(UnifiedUser(role="admin", employee_code=employee_code))
    for email in _split_env_values(
        os.getenv("SEATALK_ADMIN_EMAILS", ""),
        os.getenv("SEATALK_ADMIN_EMAIL", ""),
    ):
        users.append(UnifiedUser(role="admin", email=email.lower()))
    for seatalk_user_id in _split_env_values(
        os.getenv("SEATALK_ADMIN_SEATALK_IDS", ""),
        os.getenv("SEATALK_ADMIN_SEATALK_ID", ""),
    ):
        users.append(UnifiedUser(role="admin", seatalk_user_id=seatalk_user_id))

    return users


def _match_user(callback_context: dict[str, str], directory: list[UnifiedUser]) -> UnifiedUser | None:
    employee_code = str(callback_context.get("employee_code") or "").strip()
    email = str(callback_context.get("email") or "").strip().lower()
    seatalk_user_id = str(callback_context.get("seatalk_id") or "").strip()
    for user in directory:
        if employee_code and user.employee_code == employee_code:
            return user
        if email and user.email == email:
            return user
        if seatalk_user_id and user.seatalk_user_id == seatalk_user_id:
            return user
    return None


def build_unified_user(
    callback_context: dict[str, str],
    directory: list[UnifiedUser],
    *,
    env_directory: list[UnifiedUser] | None = None,
) -> dict[str, Any]:
    employee_code = str(callback_context.get("employee_code") or "").strip()
    email = str(callback_context.get("email") or "").strip().lower()
    seatalk_user_id = str(callback_context.get("seatalk_id") or "").strip()
    matched = _match_user(callback_context, env_directory or []) or _match_user(callback_context, directory)
    role = matched.role if matched else "guest"
    gmail = matched.gmail if matched else ""
    name = matched.name if matched else ""
    return {
        "role": role,
        "employee_code": employee_code or (matched.employee_code if matched else ""),
        "email": email or (matched.email if matched else ""),
        "seatalk_user_id": seatalk_user_id or (matched.seatalk_user_id if matched else ""),
        "gmail": gmail,
        "name": name,
    }


def get_superadmins(directory: list[UnifiedUser]) -> list[dict[str, Any]]:
    return [asdict(user) for user in directory if user.role == "superadmin"]
