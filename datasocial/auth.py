from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests

from .config import Settings
from .exceptions import DatasocialError


LOGGER = logging.getLogger("datasocial.auth")


def _load_service_account_credentials(settings: Settings) -> Any:
    try:
        from google.oauth2 import service_account
    except ImportError as exc:
        raise DatasocialError(
            "google-auth is not installed. Install dependencies from requirements.txt before using service account auth."
        ) from exc
    scopes = list(settings.google_access_token_scopes or ("https://www.googleapis.com/auth/cloud-platform",))
    if settings.google_service_account_json:
        try:
            info = json.loads(settings.google_service_account_json)
        except json.JSONDecodeError as exc:
            raise DatasocialError(
                f"DATASOCIAL_GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {exc}"
            ) from exc
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)
    if settings.google_service_account_file:
        path = Path(settings.google_service_account_file)
        if not path.exists():
            raise DatasocialError(f"Service account credential file not found: {path}")
        return service_account.Credentials.from_service_account_file(str(path), scopes=scopes)
    raise DatasocialError(
        "No service account credential configured. Set DATASOCIAL_GOOGLE_SERVICE_ACCOUNT_JSON or DATASOCIAL_GOOGLE_SERVICE_ACCOUNT_FILE."
    )


def get_google_access_token(settings: Settings) -> str:
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
    except ImportError as exc:
        raise DatasocialError(
            "google-auth is not installed. Install dependencies from requirements.txt before using service account auth."
        ) from exc
    credentials = _load_service_account_credentials(settings)
    credentials.refresh(GoogleAuthRequest())
    token = str(credentials.token or "").strip()
    if not token:
        raise DatasocialError("Google service account access token refresh returned an empty token.")
    LOGGER.info("service_account_auth=ok | phase=google_access_token_refreshed")
    return token


def exchange_google_access_token_for_usession(
    settings: Settings,
    *,
    access_token: str | None = None,
) -> str:
    token = access_token or get_google_access_token(settings)
    response = requests.get(
        settings.google_exchange_endpoint,
        params={"access_token": token},
        allow_redirects=False,
        timeout=settings.timeout,
    )
    if not response.ok and response.status_code not in {301, 302, 303, 307, 308}:
        raise DatasocialError(
            f"Google callback exchange failed with HTTP {response.status_code}: {response.text[:500]}"
        )
    session_cookie = response.cookies.get("usession")
    if not session_cookie:
        for cookie in response.cookies:
            if cookie.name == "usession" and cookie.value:
                session_cookie = cookie.value
                break
    if not session_cookie:
        set_cookie_headers = response.headers.get("set-cookie", "")
        for part in set_cookie_headers.split(","):
            part = part.strip()
            if part.startswith("usession="):
                session_cookie = part.split(";", 1)[0].split("=", 1)[1].strip()
                break
    if not session_cookie:
        raise DatasocialError(
            "Google callback exchange succeeded but no usession cookie was returned."
        )
    LOGGER.info("service_account_auth=ok | phase=usession_exchanged")
    return str(session_cookie).strip()
