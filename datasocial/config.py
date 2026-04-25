from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_ENDPOINT = "https://socialdata.garena.vn/graphql"
DEFAULT_ORIGIN = "https://socialdata.garena.vn"
DEFAULT_REFERER_TEMPLATE = "https://socialdata.garena.vn/{app_slug}/member/post"
DEFAULT_PER_PAGE = 50
DEFAULT_TIMEOUT = 30
DEFAULT_APP_ID = 0


@dataclass(slots=True)
class Settings:
    endpoint: str = DEFAULT_ENDPOINT
    origin: str = DEFAULT_ORIGIN
    usession: str = ""
    google_service_account_file: str = ""
    google_service_account_json: str = ""
    google_access_token_scopes: tuple[str, ...] = ("https://www.googleapis.com/auth/cloud-platform",)
    google_exchange_endpoint: str = "https://socialdata.garena.vn/connect/google/callback"
    timeout: int = DEFAULT_TIMEOUT
    app_id: int = DEFAULT_APP_ID
    app_slug: str = ""
    seatalk_app_id: str = ""
    seatalk_app_secret: str = ""
    seatalk_group_id: str = ""
    seatalk_employee_code: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            endpoint=os.getenv("DATASOCIAL_GRAPHQL_ENDPOINT", DEFAULT_ENDPOINT),
            origin=os.getenv("DATASOCIAL_ORIGIN", DEFAULT_ORIGIN),
            usession=os.getenv("DATASOCIAL_USESSION", "").strip(),
            google_service_account_file=os.getenv("DATASOCIAL_GOOGLE_SERVICE_ACCOUNT_FILE", "").strip(),
            google_service_account_json=os.getenv("DATASOCIAL_GOOGLE_SERVICE_ACCOUNT_JSON", "").strip(),
            google_access_token_scopes=tuple(
                value.strip()
                for value in os.getenv(
                    "DATASOCIAL_GOOGLE_ACCESS_TOKEN_SCOPES",
                    "https://www.googleapis.com/auth/cloud-platform",
                ).split(",")
                if value.strip()
            )
            or ("https://www.googleapis.com/auth/cloud-platform",),
            google_exchange_endpoint=os.getenv(
                "DATASOCIAL_GOOGLE_EXCHANGE_ENDPOINT",
                "https://socialdata.garena.vn/connect/google/callback",
            ).strip(),
            timeout=int(os.getenv("DATASOCIAL_TIMEOUT", DEFAULT_TIMEOUT)),
            app_id=int(os.getenv("DATASOCIAL_APP_ID", DEFAULT_APP_ID)),
            app_slug=os.getenv("DATASOCIAL_APP_SLUG", "").strip(),
            seatalk_app_id=os.getenv("SEATALK_APP_ID", "").strip(),
            seatalk_app_secret=os.getenv("SEATALK_APP_SECRET", "").strip(),
            seatalk_group_id=os.getenv("SEATALK_GROUP_ID", "").strip(),
            seatalk_employee_code=os.getenv("SEATALK_EMPLOYEE_CODE", "").strip(),
        )

    @property
    def referer(self) -> str:
        if self.app_slug:
            return DEFAULT_REFERER_TEMPLATE.format(app_slug=self.app_slug)
        return f"{self.origin}/"

    @property
    def has_service_account_auth(self) -> bool:
        return bool(self.google_service_account_file or self.google_service_account_json)
