from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from datasocial.seatalk import SeaTalkClient, SeaTalkSettings


LOGGER = logging.getLogger("seatalk.uploadimage")

DEFAULT_IMAGE_STORE_PATH = Path("outputs/seatalk_private_images.json")
DEFAULT_VENDOR_UPLOAD_URL = "https://vendors.garena.vn/upload-tool"
DEFAULT_VENDOR_PUBLIC_URL_PREFIX = "https://files.garena.vn/garena-social/public/"


class UploadImageError(RuntimeError):
    """Raised when the uploadimage command cannot complete."""


def get_image_store_path() -> Path:
    raw_path = os.getenv("SEATALK_PRIVATE_IMAGE_STORE_PATH", "").strip()
    return Path(raw_path) if raw_path else DEFAULT_IMAGE_STORE_PATH


def _load_store(store_path: Path) -> dict[str, Any]:
    if not store_path.exists():
        return {"users": {}}
    return json.loads(store_path.read_text(encoding="utf-8"))


def _save_store(store_path: Path, payload: dict[str, Any]) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = store_path.with_suffix(f"{store_path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(store_path)


def store_latest_image_for_user(
    store_path: Path,
    *,
    employee_code: str,
    seatalk_id: str,
    message_id: str,
    image_url: str,
    thread_id: str = "",
) -> dict[str, Any]:
    payload = _load_store(store_path)
    entry = {
        "employee_code": employee_code,
        "seatalk_id": seatalk_id,
        "message_id": message_id,
        "thread_id": thread_id,
        "image_url": image_url,
        "stored_at": datetime.now().isoformat(timespec="seconds"),
        "processed": False,
    }
    payload.setdefault("users", {})[employee_code] = entry
    _save_store(store_path, payload)
    LOGGER.info(
        "Seatalk image stored | employee_code=%s | message_id=%s | image_url=%s",
        employee_code,
        message_id,
        image_url,
    )
    return entry


def get_latest_unprocessed_image_for_user(store_path: Path, *, employee_code: str) -> dict[str, Any] | None:
    payload = _load_store(store_path)
    entry = (payload.get("users") or {}).get(employee_code)
    if not isinstance(entry, dict):
        return None
    if entry.get("processed"):
        return None
    return entry


def mark_image_processed_for_user(store_path: Path, *, employee_code: str) -> None:
    payload = _load_store(store_path)
    entry = (payload.get("users") or {}).get(employee_code)
    if not isinstance(entry, dict):
        return
    entry["processed"] = True
    entry["processed_at"] = datetime.now().isoformat(timespec="seconds")
    _save_store(store_path, payload)
    LOGGER.info("Seatalk image marked processed | employee_code=%s", employee_code)


def _guess_extension(response: requests.Response, image_url: str) -> str:
    content_type = str(response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if content_type in mapping:
        return mapping[content_type]
    suffix = Path(image_url).suffix
    return suffix if suffix else ".jpg"


def _safe_filename_stem(filename_hint: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(filename_hint or "").strip()).strip("-")
    return cleaned[:60] or "seatalk-image"


def _filename_match_tokens(image_path: Path) -> list[str]:
    stem = image_path.stem
    tokens = [image_path.name, stem]
    if len(stem) >= 16:
        tokens.append(stem[:16])
        tokens.append(stem[-16:])
    return [token for token in tokens if token]


def download_seatalk_image(
    *,
    image_url: str,
    app_id: str,
    app_secret: str,
    filename_hint: str = "",
    output_dir: Path | None = None,
) -> Path:
    client = SeaTalkClient(SeaTalkSettings(app_id=app_id, app_secret=app_secret))
    token = client.get_app_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(image_url, headers=headers, timeout=60)
    if not response.ok:
        LOGGER.error(
            "Seatalk image download failed | status=%s | image_url=%s",
            response.status_code,
            image_url,
        )
        raise UploadImageError(f"Seatalk media download failed with HTTP {response.status_code}.")

    target_dir = output_dir or Path(tempfile.mkdtemp(prefix="seatalk-uploadimage-"))
    target_dir.mkdir(parents=True, exist_ok=True)
    extension = _guess_extension(response, image_url)
    image_path = target_dir / f"{_safe_filename_stem(filename_hint)}{extension}"
    image_path.write_bytes(response.content)
    LOGGER.info(
        "Seatalk image download success | image_url=%s | bytes=%s | path=%s",
        image_url,
        len(response.content),
        image_path,
    )
    return image_path


def _extract_public_urls(page_content: str, *, public_url_prefix: str) -> list[str]:
    pattern = re.compile(re.escape(public_url_prefix) + r"[^\s\"'<>]+")
    results: list[str] = []
    for match in pattern.findall(page_content):
        clean = match.split("?", 1)[0].rstrip("),.;")
        if clean not in results:
            results.append(clean)
    return results


def summarize_upload_error(exc: Exception) -> str:
    text = str(exc or "").strip()
    lowered = text.lower()
    if "libglib-2.0.so.0" in text or "loading shared libraries" in lowered:
        return "Runtime Railway dang thieu Linux libraries cho Chromium."
    if "executable doesn't exist" in lowered:
        return "Playwright browser chua duoc cai day du trong Railway runtime."
    if "website auth failed" in lowered:
        return "Khong dang nhap duoc vao Vendor Tool bang cookie hien tai."
    if "public url" in lowered:
        return "Khong tim thay link anh public moi sau khi bam Save."
    if "save button was not clickable" in lowered:
        return "Khong bam duoc nut Save tren Vendor Tool."
    if "upload input not found" in lowered:
        return "Khong tim thay o upload file tren Vendor Tool."
    if len(text) > 180:
        return text[:177].rstrip() + "..."
    return text or "Da xay ra loi ngoai du kien."


def upload_image_to_vendor_tool(image_path: Path) -> str:
    upload_url = os.getenv("VENDOR_UPLOAD_TOOL_URL", DEFAULT_VENDOR_UPLOAD_URL).strip() or DEFAULT_VENDOR_UPLOAD_URL
    auth_token = os.getenv("VENDOR_AUTH_TOKEN", "").strip()
    cookie_name = os.getenv("VENDOR_AUTH_COOKIE_NAME", "token").strip() or "token"
    cookie_domain = os.getenv("VENDOR_AUTH_COOKIE_DOMAIN", "vendors.garena.vn").strip() or "vendors.garena.vn"
    public_url_prefix = (
        os.getenv("VENDOR_PUBLIC_URL_PREFIX", DEFAULT_VENDOR_PUBLIC_URL_PREFIX).strip()
        or DEFAULT_VENDOR_PUBLIC_URL_PREFIX
    )
    headless = os.getenv("VENDOR_UPLOAD_HEADLESS", "true").strip().lower() not in {"0", "false", "no"}
    timeout_ms = int(os.getenv("VENDOR_UPLOAD_TIMEOUT_MS", "60000").strip() or "60000")
    result_timeout_ms = int(os.getenv("VENDOR_UPLOAD_RESULT_TIMEOUT_MS", "15000").strip() or "15000")

    if not auth_token:
        raise UploadImageError("Missing VENDOR_AUTH_TOKEN.")

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise UploadImageError(
            "Playwright is not installed in the runtime. Install `playwright` and Chromium first."
        ) from exc

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=headless)
        except Exception as exc:
            raise UploadImageError(summarize_upload_error(exc)) from exc

        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": cookie_name,
                    "value": auth_token,
                    "domain": cookie_domain,
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                }
            ]
        )
        page = context.new_page()

        try:
            page.goto(upload_url, wait_until="domcontentloaded", timeout=timeout_ms)
            upload_zone = page.locator(".ant-upload-drag-container").first
            upload_zone.wait_for(timeout=timeout_ms)
            LOGGER.info("Vendor upload auth success | url=%s", upload_url)
        except PlaywrightTimeoutError as exc:
            LOGGER.error("Vendor upload auth failed | url=%s", upload_url)
            browser.close()
            raise UploadImageError("Website auth failed or upload area did not appear.") from exc

        file_input = page.locator("input[type='file']").first
        if file_input.count() <= 0:
            browser.close()
            raise UploadImageError("Upload input not found on vendor tool page.")

        file_input.set_input_files(str(image_path))
        page.get_by_text(image_path.name, exact=False).wait_for(timeout=timeout_ms)
        LOGGER.info("Vendor upload success | image_path=%s", image_path)

        checkbox = page.locator("input[type='checkbox']").first
        if checkbox.count() > 0:
            try:
                if checkbox.is_checked():
                    checkbox.uncheck(force=True)
                    LOGGER.info("Vendor sensitive-data checkbox unchecked before save | image_path=%s", image_path)
            except Exception:
                LOGGER.exception("Vendor checkbox state change failed | image_path=%s", image_path)

        existing_urls = _extract_public_urls(page.content(), public_url_prefix=public_url_prefix)
        try:
            page.get_by_role("button", name="Save").click(timeout=timeout_ms)
            LOGGER.info("Vendor save click success | image_path=%s", image_path)
        except PlaywrightTimeoutError as exc:
            LOGGER.error("Vendor save click failed | image_path=%s", image_path)
            browser.close()
            raise UploadImageError("Save button was not clickable.") from exc

        filename_tokens = _filename_match_tokens(image_path)
        LOGGER.info(
            "Waiting for vendor result URL | image_path=%s | timeout_ms=%s | existing_urls=%s | filename_tokens=%s",
            image_path,
            result_timeout_ms,
            len(existing_urls),
            filename_tokens,
        )
        deadline = time.monotonic() + (result_timeout_ms / 1000)
        new_urls: list[str] = []
        matched_row_found = False
        while time.monotonic() < deadline:
            row_match = None
            for token in filename_tokens:
                candidate = page.locator("tbody tr", has_text=token).last
                if candidate.count() > 0:
                    row_match = candidate
                    break
            if row_match is not None:
                row_html = row_match.inner_html()
                row_urls = _extract_public_urls(row_html, public_url_prefix=public_url_prefix)
                new_urls = [url for url in row_urls if url not in existing_urls]
                if new_urls:
                    matched_row_found = True
                    break
            if int((deadline - time.monotonic()) * 1000) > 1500:
                try:
                    page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
                except PlaywrightTimeoutError:
                    LOGGER.warning("Vendor page reload timed out while waiting for result | image_path=%s", image_path)
            page.wait_for_timeout(1000)

        if matched_row_found and new_urls:
            LOGGER.info(
                "Vendor result row matched uploaded file | image_path=%s | urls=%s",
                image_path,
                new_urls,
            )
        else:
            LOGGER.warning(
                "Vendor result row with uploaded file did not produce a new public URL | image_path=%s | timeout_ms=%s",
                image_path,
                result_timeout_ms,
            )
        browser.close()

    final_url = (new_urls or [""])[0]
    if not final_url.startswith(public_url_prefix):
        LOGGER.error("Vendor result URL not found | image_path=%s", image_path)
        raise UploadImageError("Da bam Save nhung khong thay dong ket qua khop voi file vua upload tren Vendor Tool.")
    LOGGER.info("Vendor result URL found | url=%s", final_url)
    return final_url


def send_seatalk_text_reply(client: SeaTalkClient, content: str) -> dict[str, Any]:
    result = client.send_text(content)
    LOGGER.info("Seatalk reply success | content_preview=%s", content[:120].replace("\n", " "))
    return result
