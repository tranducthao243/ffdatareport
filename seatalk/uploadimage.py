from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from datasocial.seatalk import SeaTalkClient, SeaTalkSettings


LOGGER = logging.getLogger("seatalk.uploadimage")

DEFAULT_IMAGE_STORE_PATH = Path("outputs/seatalk_private_images.json")
DEFAULT_VENDOR_UPLOAD_URL = "https://vendors.garena.vn/upload-tool"
DEFAULT_VENDOR_PUBLIC_URL_PREFIX = "https://files.garena.vn/garena-social/public/"
DEFAULT_REMOVEBG_SPACE_ID = "amirgame197/Remove-Background"
DEFAULT_REMOVEBG_API_NAME = "/predict"
DEFAULT_SEATALK_IMAGE_MAX_BYTES = 3_600_000


class UploadImageError(RuntimeError):
    """Raised when the uploadimage command cannot complete."""


def _log_flow_step(flow: str, step: str, status: str, **details: Any) -> None:
    detail_parts = [f"{key}={value}" for key, value in details.items() if value not in (None, "")]
    suffix = f" | {' | '.join(detail_parts)}" if detail_parts else ""
    message = f"{flow} step | step={step} | status={status}{suffix}"
    if status == "fail":
        LOGGER.error(message)
    elif status == "warn":
        LOGGER.warning(message)
    else:
        LOGGER.info(message)


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


def _normalize_processed_commands(entry: dict[str, Any]) -> list[str]:
    commands = entry.get("processed_commands")
    if isinstance(commands, list):
        return [str(item).strip() for item in commands if str(item).strip()]
    if entry.get("processed"):
        return ["uploadimage", "removebg"]
    return []


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
        "processed_commands": [],
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


def get_latest_unprocessed_image_for_user(
    store_path: Path,
    *,
    employee_code: str,
    command_name: str,
) -> dict[str, Any] | None:
    payload = _load_store(store_path)
    entry = (payload.get("users") or {}).get(employee_code)
    if not isinstance(entry, dict):
        return None
    processed_commands = _normalize_processed_commands(entry)
    if command_name in processed_commands:
        return None
    return entry


def mark_image_processed_for_user(
    store_path: Path,
    *,
    employee_code: str,
    message_id: str,
    command_name: str,
) -> None:
    payload = _load_store(store_path)
    entry = (payload.get("users") or {}).get(employee_code)
    if not isinstance(entry, dict):
        return
    if str(entry.get("message_id") or "") != str(message_id or ""):
        LOGGER.info(
            "Skip marking processed because latest stored image changed | employee_code=%s | expected_message_id=%s | current_message_id=%s | command=%s",
            employee_code,
            message_id,
            entry.get("message_id") or "-",
            command_name,
        )
        return
    processed_commands = _normalize_processed_commands(entry)
    if command_name not in processed_commands:
        processed_commands.append(command_name)
    entry["processed_commands"] = processed_commands
    entry["processed"] = len(processed_commands) >= 2
    entry["processed_at"] = datetime.now().isoformat(timespec="seconds")
    _save_store(store_path, payload)
    LOGGER.info(
        "Seatalk image marked processed | employee_code=%s | message_id=%s | command=%s | processed_commands=%s",
        employee_code,
        message_id,
        command_name,
        processed_commands,
    )


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
    token_source = str(filename_hint or cleaned or "seatalk-image")
    token = hashlib.sha1(token_source.encode("utf-8")).hexdigest()[:12]
    prefix = cleaned[:12] or "seatalk"
    return f"{prefix}-{token}"


def _filename_match_tokens(image_path: Path) -> list[str]:
    stem = image_path.stem
    tokens = [image_path.name, stem]
    if "-" in stem:
        tokens.append(stem.rsplit("-", 1)[-1])
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
    _log_flow_step(
        "seatalk_download",
        "download_media",
        "ok",
        bytes=len(response.content),
        image_path=image_path,
    )
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


def _extract_top_row_public_url(page, *, public_url_prefix: str) -> str:
    row = page.locator("tbody tr").first
    if row.count() <= 0:
        return ""
    html = row.inner_html()
    urls = _extract_public_urls(html, public_url_prefix=public_url_prefix)
    return urls[0] if urls else ""


def _extract_vendor_table_rows(page) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    row_locator = page.locator("tbody tr")
    row_count = row_locator.count()
    for index in range(row_count):
        row = row_locator.nth(index)
        cells = row.locator("td")
        if cells.count() < 4:
            continue
        file_url = cells.nth(1).inner_text().strip()
        file_name = cells.nth(2).inner_text().strip()
        created_at = cells.nth(3).inner_text().strip()
        if not file_url:
            anchors = cells.nth(1).locator("a")
            if anchors.count() > 0:
                file_url = anchors.first.inner_text().strip()
        if not file_name:
            anchors = cells.nth(2).locator("a")
            if anchors.count() > 0:
                file_name = anchors.first.inner_text().strip()
        if not file_name and file_url:
            file_name = Path(file_url.split("?", 1)[0]).name
        rows.append(
            {
                "file_url": file_url,
                "file_name": file_name,
                "created_at": created_at,
            }
        )
    return rows


def _clean_vendor_table_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        normalized = {
            "file_url": str(row.get("file_url") or "").strip(),
            "file_name": str(row.get("file_name") or "").strip(),
            "created_at": str(row.get("created_at") or "").strip(),
        }
        if not any(normalized.values()):
            continue
        key = (normalized["file_url"], normalized["file_name"], normalized["created_at"])
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    return cleaned


def _normalize_vendor_filename(value: str) -> str:
    return Path(str(value or "").strip()).name.lower()


def _wait_for_vendor_table_rows(page, *, timeout_ms: int) -> list[dict[str, str]]:
    deadline = time.monotonic() + (timeout_ms / 1000)
    latest_rows: list[dict[str, str]] = []
    while time.monotonic() < deadline:
        latest_rows = _clean_vendor_table_rows(_extract_vendor_table_rows(page))
        if any(row.get("file_url") or row.get("created_at") for row in latest_rows):
            return latest_rows
        page.wait_for_timeout(500)
    return latest_rows


def summarize_upload_error(exc: Exception) -> str:
    text = str(exc or "").strip()
    lowered = text.lower()
    if "libglib-2.0.so.0" in text or "loading shared libraries" in lowered:
        return "Runtime Railway dang thieu Linux libraries cho Chromium."
    if "executable doesn't exist" in lowered:
        return "Playwright browser chua duoc cai day du trong Railway runtime."
    if "website auth failed" in lowered:
        return "Khong dang nhap duoc vao Vendor Tool bang cookie hien tai."
    if "chua upload xong file vao he thong" in lowered:
        return "Vendor Tool chua upload xong file vao he thong, nen bot da dung lai truoc khi bam Save."
    if "khong bo tick duoc" in lowered:
        return "Bot khong bo duoc o tick du lieu nhay cam tren Vendor Tool."
    if "valid length/size limit" in lowered or "4001" in lowered:
        return "SeaTalk tu choi anh tra ve vi vuot gioi han kich thuoc/noi dung hop le."
    if "message cannot be empty" in lowered or "4003" in lowered:
        return "SeaTalk tu choi payload anh tra ve. Can doi sang cach gui file/anh phu hop hon voi API hien tai."
    if "public url" in lowered:
        return "Khong tim thay link anh public moi sau khi bam Save."
    if "save button was not clickable" in lowered:
        return "Khong bam duoc nut Save tren Vendor Tool."
    if "upload input not found" in lowered:
        return "Khong tim thay o upload file tren Vendor Tool."
    if len(text) > 180:
        return text[:177].rstrip() + "..."
    return text or "Da xay ra loi ngoai du kien."


def _normalize_result_asset(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, (list, tuple)):
        for item in result:
            normalized = _normalize_result_asset(item)
            if normalized:
                return normalized
        return ""
    if isinstance(result, dict):
        for key in ("path", "url", "name"):
            value = str(result.get(key) or "").strip()
            if value:
                return value
        for key in ("image", "data", "value"):
            value = result.get(key)
            normalized = _normalize_result_asset(value)
            if normalized:
                return normalized
    return ""


def _download_or_copy_result_asset(
    asset_ref: str,
    *,
    filename_hint: str,
    output_dir: Path | None = None,
) -> Path:
    target_dir = output_dir or Path(tempfile.mkdtemp(prefix="seatalk-removebg-"))
    target_dir.mkdir(parents=True, exist_ok=True)
    asset_text = str(asset_ref or "").strip()
    suffix = Path(asset_text).suffix or ".png"
    target_path = target_dir / f"{_safe_filename_stem(filename_hint)}{suffix}"

    if asset_text.startswith("http://") or asset_text.startswith("https://"):
        response = requests.get(asset_text, timeout=120)
        response.raise_for_status()
        target_path.write_bytes(response.content)
        return target_path

    source_path = Path(asset_text)
    if not source_path.exists():
        raise UploadImageError("Remove background API did not return a usable file.")
    shutil.copyfile(source_path, target_path)
    return target_path


def convert_image_to_png(image_path: Path) -> Path:
    if image_path.suffix.lower() == ".png":
        target_path = image_path
    else:
        target_path = image_path.with_suffix(".png")
        with Image.open(image_path) as image:
            image.convert("RGBA").save(target_path, format="PNG", optimize=True)
        LOGGER.info("Converted image to PNG for SeaTalk delivery | source=%s | output=%s", image_path, target_path)

    max_bytes = int(os.getenv("SEATALK_IMAGE_MAX_BYTES", str(DEFAULT_SEATALK_IMAGE_MAX_BYTES)).strip() or str(DEFAULT_SEATALK_IMAGE_MAX_BYTES))
    if target_path.stat().st_size <= max_bytes:
        return target_path

    with Image.open(target_path) as image:
        working = image.convert("RGBA")
        width, height = working.size
        attempt = 0
        while target_path.stat().st_size > max_bytes and width > 512 and height > 512 and attempt < 6:
            width = max(int(width * 0.85), 512)
            height = max(int(height * 0.85), 512)
            resized = working.resize((width, height), Image.LANCZOS)
            resized.save(target_path, format="PNG", optimize=True)
            attempt += 1
            LOGGER.info(
                "Reduced PNG size for SeaTalk delivery | path=%s | attempt=%s | width=%s | height=%s | bytes=%s",
                target_path,
                attempt,
                width,
                height,
                target_path.stat().st_size,
            )
        if target_path.stat().st_size > max_bytes:
            quantized = working.convert("P", palette=Image.ADAPTIVE, colors=255)
            quantized.save(target_path, format="PNG", optimize=True, transparency=0)
            LOGGER.info("Quantized PNG for SeaTalk delivery | path=%s | bytes=%s", target_path, target_path.stat().st_size)
    return target_path


def remove_background_with_space(image_path: Path) -> Path:
    space_id = os.getenv("REMOVEBG_SPACE_ID", DEFAULT_REMOVEBG_SPACE_ID).strip() or DEFAULT_REMOVEBG_SPACE_ID
    api_name = os.getenv("REMOVEBG_API_NAME", DEFAULT_REMOVEBG_API_NAME).strip() or DEFAULT_REMOVEBG_API_NAME
    hf_token = os.getenv("REMOVEBG_HF_TOKEN", "").strip()

    try:
        from gradio_client import Client, handle_file
    except ImportError as exc:
        raise UploadImageError("gradio_client is not installed in the runtime.") from exc

    try:
        client_kwargs: dict[str, Any] = {}
        if hf_token:
            client_kwargs["hf_token"] = hf_token
        client = Client(space_id, **client_kwargs)
        result = client.predict(
            image=handle_file(str(image_path)),
            api_name=api_name,
        )
    except Exception as exc:
        raise UploadImageError(f"Remove background API failed: {exc}") from exc

    asset_ref = _normalize_result_asset(result)
    if not asset_ref:
        raise UploadImageError("Remove background API did not return an image result.")
    _log_flow_step("removebg", "space_predict", "ok", space_id=space_id, api_name=api_name)

    output_path = _download_or_copy_result_asset(
        asset_ref,
        filename_hint=f"{image_path.stem}-removebg",
    )
    output_path = convert_image_to_png(output_path)
    _log_flow_step("removebg", "prepare_png_result", "ok", output_path=output_path, bytes=output_path.stat().st_size)
    LOGGER.info(
        "Remove background success | source=%s | output=%s | asset_ref=%s",
        image_path,
        output_path,
        asset_ref,
    )
    return output_path


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
            _log_flow_step("vendor_upload", "auth_and_open_page", "ok", upload_url=upload_url)
            LOGGER.info("Vendor upload auth success | url=%s", upload_url)
        except PlaywrightTimeoutError as exc:
            _log_flow_step("vendor_upload", "auth_and_open_page", "fail", upload_url=upload_url)
            LOGGER.error("Vendor upload auth failed | url=%s", upload_url)
            browser.close()
            raise UploadImageError("Website auth failed or upload area did not appear.") from exc

        file_input = page.locator("input[type='file']").first
        if file_input.count() <= 0:
            _log_flow_step("vendor_upload", "find_file_input", "fail", image_path=image_path)
            browser.close()
            raise UploadImageError("Upload input not found on vendor tool page.")
        _log_flow_step("vendor_upload", "find_file_input", "ok", image_path=image_path)

        existing_rows = _wait_for_vendor_table_rows(page, timeout_ms=min(timeout_ms, 8000))
        existing_urls = [
            row["file_url"]
            for row in existing_rows
            if row.get("file_url", "").startswith(public_url_prefix)
        ]
        existing_row_count = len(existing_rows)
        existing_top_row = existing_rows[0] if existing_rows else {"file_url": "", "file_name": "", "created_at": ""}
        LOGGER.info(
            "Vendor URLs before save | image_path=%s | row_count=%s | rows=%s",
            image_path,
            existing_row_count,
            existing_rows,
        )
        _log_flow_step("vendor_upload", "snapshot_before_save", "ok", row_count=existing_row_count)

        file_input.set_input_files(str(image_path))
        page.get_by_text(image_path.name, exact=False).wait_for(timeout=timeout_ms)
        _log_flow_step("vendor_upload", "select_file", "ok", image_name=image_path.name)
        try:
            page.wait_for_function(
                """() => {
                    const uploading = document.querySelectorAll('.ant-upload-list-item-uploading').length;
                    const done = document.querySelectorAll('.ant-upload-list-item-done').length;
                    return uploading === 0 && done > 0;
                }""",
                timeout=min(timeout_ms, 8000),
            )
            page.wait_for_timeout(1000)
            _log_flow_step("vendor_upload", "wait_upload_component", "ok", image_name=image_path.name)
            LOGGER.info("Vendor upload component finished | image_path=%s", image_path)
        except PlaywrightTimeoutError:
            _log_flow_step("vendor_upload", "wait_upload_component", "warn", image_name=image_path.name)
            LOGGER.warning(
                "Vendor upload component did not expose a done state before timeout | image_path=%s",
                image_path,
            )
            page.wait_for_timeout(2000)
        _log_flow_step("vendor_upload", "upload_to_component", "ok", image_path=image_path)
        LOGGER.info("Vendor upload success | image_path=%s", image_path)

        checkbox = page.locator("input#basic_isSensitive").first
        if checkbox.count() > 0:
            try:
                if checkbox.is_checked():
                    unchecked = page.evaluate(
                        """() => {
                            const checkbox = document.querySelector('#basic_isSensitive') || document.querySelector('input[type="checkbox"]');
                            if (!checkbox) return false;
                            checkbox.checked = false;
                            checkbox.dispatchEvent(new Event('input', { bubbles: true }));
                            checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                            return checkbox.checked === false;
                        }"""
                    )
                    if not unchecked:
                        raise UploadImageError("Khong bo tick duoc o du lieu nhay cam tren Vendor Tool.")
                    _log_flow_step("vendor_upload", "unset_sensitive_checkbox", "ok", image_path=image_path)
                    LOGGER.info("Vendor sensitive-data checkbox unchecked before save | image_path=%s", image_path)
            except Exception:
                _log_flow_step("vendor_upload", "unset_sensitive_checkbox", "fail", image_path=image_path)
                LOGGER.exception("Vendor checkbox state change failed | image_path=%s", image_path)

        try:
            try:
                page.get_by_role("button", name="Save").click(timeout=timeout_ms)
            except PlaywrightTimeoutError:
                page.locator("button[type='submit'].ant-btn-primary").first.click(timeout=timeout_ms)
            _log_flow_step("vendor_upload", "click_save", "ok", image_path=image_path)
            LOGGER.info("Vendor save click success | image_path=%s", image_path)
        except PlaywrightTimeoutError as exc:
            _log_flow_step("vendor_upload", "click_save", "fail", image_path=image_path)
            LOGGER.error("Vendor save click failed | image_path=%s", image_path)
            browser.close()
            raise UploadImageError("Save button was not clickable.") from exc

        LOGGER.info(
            "Waiting for vendor result URL | image_path=%s | timeout_ms=%s | existing_urls=%s",
            image_path,
            result_timeout_ms,
            len(existing_urls),
        )
        deadline = time.monotonic() + (result_timeout_ms / 1000)
        final_candidates: list[dict[str, str]] = []
        final_row_count = existing_row_count
        while time.monotonic() < deadline:
            try:
                page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                LOGGER.warning("Vendor page reload timed out while waiting for result | image_path=%s", image_path)
            current_rows = _wait_for_vendor_table_rows(page, timeout_ms=3000)
            current_row_count = len(current_rows)
            current_top_row = current_rows[0] if current_rows else {"file_url": "", "file_name": "", "created_at": ""}
            final_candidates = []
            if (
                current_top_row.get("file_url", "").startswith(public_url_prefix)
                and current_top_row.get("file_url", "") not in existing_urls
                and (
                    current_top_row.get("created_at", "") != existing_top_row.get("created_at", "")
                    or current_top_row.get("file_url", "") != existing_top_row.get("file_url", "")
                )
            ):
                final_candidates.append(current_top_row)
            if len(final_candidates) == 1:
                final_row_count = current_row_count
                break
            page.wait_for_timeout(1000)

        LOGGER.info(
            "Vendor URLs after save | image_path=%s | row_count=%s | top_before=%s | new_rows=%s",
            image_path,
            final_row_count,
            existing_top_row,
            final_candidates,
        )
        _log_flow_step(
            "vendor_upload",
            "read_rows_after_save",
            "ok" if len(final_candidates) == 1 else "warn",
            row_count=final_row_count,
            candidates=len(final_candidates),
        )
        browser.close()

    if len(final_candidates) > 1:
        _log_flow_step("vendor_upload", "finalize_public_url", "fail", candidates=len(final_candidates))
        LOGGER.error("Vendor result URL ambiguous | image_path=%s | candidates=%s", image_path, final_candidates)
        raise UploadImageError("Vendor Tool tra ve nhieu link moi cung luc, khong xac dinh duoc link cua anh vua upload.")

    final_url = final_candidates[0].get("file_url", "") if final_candidates else ""
    if not final_url.startswith(public_url_prefix):
        _log_flow_step("vendor_upload", "finalize_public_url", "fail", image_path=image_path)
        LOGGER.error("Vendor result URL not found | image_path=%s", image_path)
        raise UploadImageError("Da bam Save nhung khong thay public URL moi nao xuat hien sau khi luu.")
    _log_flow_step("vendor_upload", "finalize_public_url", "ok", final_url=final_url)
    LOGGER.info("Vendor result URL found | url=%s", final_url)
    return final_url


def send_seatalk_text_reply(client: SeaTalkClient, content: str) -> dict[str, Any]:
    result = client.send_text(content)
    LOGGER.info("Seatalk reply success | content_preview=%s", content[:120].replace("\n", " "))
    return result


def send_seatalk_image_reply(client: SeaTalkClient, image_path: Path) -> dict[str, Any]:
    _log_flow_step("seatalk_reply", "send_image_reply", "pending", image_path=image_path, bytes=image_path.stat().st_size)
    result = client.send_image_path(image_path)
    _log_flow_step("seatalk_reply", "send_image_reply", "ok", image_path=image_path, bytes=image_path.stat().st_size)
    LOGGER.info("Seatalk image reply success | image_path=%s | bytes=%s", image_path, image_path.stat().st_size)
    return result
