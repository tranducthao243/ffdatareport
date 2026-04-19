from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .exceptions import DatasocialError


SEATALK_OPENAPI_BASE = "https://openapi.seatalk.io"


class SeaTalkError(DatasocialError):
    """SeaTalk delivery error."""


@dataclass(slots=True)
class SeaTalkSettings:
    app_id: str
    app_secret: str
    group_id: str = ""
    employee_code: str = ""
    use_markdown: bool = True
    usable_platform: str = "all"


class SeaTalkClient:
    def __init__(self, settings: SeaTalkSettings):
        self.settings = settings
        self.session = requests.Session()
        self.token: str | None = None

    def get_app_access_token(self) -> str:
        response = self.session.post(
            f"{SEATALK_OPENAPI_BASE}/auth/app_access_token",
            json={
                "app_id": self.settings.app_id,
                "app_secret": self.settings.app_secret,
            },
            timeout=30,
        )
        if not response.ok:
            raise SeaTalkError(
                f"SeaTalk token request failed with HTTP {response.status_code}: {response.text[:500]}"
            )
        data = response.json()
        token = data.get("app_access_token")
        if data.get("code") not in (0, "0") or not token:
            raise SeaTalkError(f"SeaTalk token response invalid: {data}")
        self.token = token
        return token

    def send_text(self, content: str) -> dict[str, Any]:
        return self.send_message(
            {
                "tag": "text",
                "text": {
                    "format": 1 if self.settings.use_markdown else 2,
                    "content": content,
                },
            }
        )

    def send_interactive(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.send_message(payload)

    def send_message(self, message: dict[str, Any]) -> dict[str, Any]:
        token = self.token or self.get_app_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        message_payload = {"message": message}

        if self.settings.group_id:
            payload = {"group_id": self.settings.group_id, **message_payload}
            url = f"{SEATALK_OPENAPI_BASE}/messaging/v2/group_chat"
        elif self.settings.employee_code:
            payload = {
                "employee_code": self.settings.employee_code,
                "usable_platform": self.settings.usable_platform,
                **message_payload,
            }
            url = f"{SEATALK_OPENAPI_BASE}/messaging/v2/single_chat"
        else:
            raise SeaTalkError("SeaTalk target missing. Set group_id or employee_code.")

        response = self.session.post(url, headers=headers, json=payload, timeout=30)
        if not response.ok:
            raise SeaTalkError(
                f"SeaTalk send failed with HTTP {response.status_code}: {response.text[:500]}"
            )
        data = response.json()
        if data.get("code") not in (0, "0", None):
            raise SeaTalkError(f"SeaTalk send returned non-zero code: {data}")
        return data
