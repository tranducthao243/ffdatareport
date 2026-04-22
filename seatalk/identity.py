from __future__ import annotations

import json
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


def build_unified_user(callback_context: dict[str, str], directory: list[UnifiedUser]) -> dict[str, Any]:
    employee_code = str(callback_context.get("employee_code") or "").strip()
    email = str(callback_context.get("email") or "").strip().lower()
    seatalk_user_id = str(callback_context.get("seatalk_id") or "").strip()
    matched = None
    for user in directory:
        if employee_code and user.employee_code == employee_code:
            matched = user
            break
        if email and user.email == email:
            matched = user
            break
        if seatalk_user_id and user.seatalk_user_id == seatalk_user_id:
            matched = user
            break
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
