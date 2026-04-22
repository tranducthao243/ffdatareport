from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import zipfile

import requests

from app.pipeline import build_report_package_by_code
from app.config_loader import load_json
from app.data_chat import answer_data_question
from app.health import (
    build_health_snapshot,
    classify_private_command,
    format_hashtag_report,
    format_data_report,
    format_health_report,
    format_scope_report,
)
from datasocial.exceptions import DatasocialError
from datasocial.presets import load_preset

from .auth import build_seatalk_client
from .callbacks import (
    SeatalkCallbackError,
    build_callback_context,
    extract_click_value,
    parse_click_payload,
)
from .uploadimage import (
    UploadImageError,
    download_seatalk_image,
    get_image_store_path,
    get_latest_unprocessed_image_for_user,
    mark_image_processed_for_user,
    remove_background_with_space,
    send_seatalk_image_reply,
    send_seatalk_text_reply,
    store_latest_image_for_user,
    summarize_upload_error,
    upload_image_to_vendor_tool,
)


LOGGER = logging.getLogger("seatalk.callback_server")


PRIVATE_FUTURE_FEATURE_MESSAGE = (
    "**Đang check và sẽ cập nhật tính năng sau**\n"
    "*Tính năng này đã được ghi nhận trong roadmap của bot.*"
)


def _is_authorized_private_sender(runtime: dict[str, Any], callback_context: dict[str, str]) -> bool:
    admin_codes = set(runtime.get("admin_employee_codes") or [])
    admin_emails = set(runtime.get("admin_emails") or [])
    admin_seatalk_ids = set(runtime.get("admin_seatalk_ids") or [])
    if not (admin_codes or admin_emails or admin_seatalk_ids):
        return True
    employee_code = callback_context["employee_code"]
    email = callback_context["email"].lower()
    seatalk_id = callback_context["seatalk_id"]
    return (
        employee_code in admin_codes
        or (email and email in admin_emails)
        or (seatalk_id and seatalk_id in admin_seatalk_ids)
    )


def _format_private_access_denied(callback_context: dict[str, str], *, contact_email: str) -> str:
    return (
        "**Bot chỉ nhận lệnh private từ admin đã được cấp quyền.**\n"
        f"*Vui lòng liên hệ {contact_email} để được thêm quyền.*\n"
        "\n"
        "*Thông tin định danh hiện tại của bạn:*\n"
        f"- employee_code: `{callback_context.get('employee_code') or '-'}`\n"
        f"- email: `{callback_context.get('email') or '-'}`\n"
        f"- seatalk_id: `{callback_context.get('seatalk_id') or '-'}`"
    )


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seatalk-callback-server",
        description="Receive SeaTalk interactive callbacks and reply with report data.",
    )
    parser.add_argument("--host", default=os.getenv("SEATALK_CALLBACK_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("SEATALK_CALLBACK_PORT", "5000")))
    parser.add_argument("--db-path", type=Path, default=Path(os.getenv("DATAMASTER_STORE_PATH", "outputs/ffvn_master.sqlite")))
    parser.add_argument("--groups-config", type=Path, default=Path(os.getenv("DATAMASTER_GROUPS_CONFIG", "config/groups.json")))
    parser.add_argument("--reports-config", type=Path, default=Path(os.getenv("DATAMASTER_REPORTS_CONFIG", "config/reports.json")))
    parser.add_argument("--campaigns-config", type=Path, default=Path(os.getenv("DATAMASTER_CAMPAIGNS_CONFIG", "config/campaigns.json")))
    parser.add_argument("--preset", default=os.getenv("DATASOCIAL_CALLBACK_PRESET", "ffvn_master_daily"))
    parser.add_argument("--report-mode", default=os.getenv("DATAMASTER_REPORT_MODE", "today_so_far"))
    parser.add_argument("--report-timezone", default=os.getenv("DATAMASTER_REPORT_TIMEZONE", "Asia/Ho_Chi_Minh"))
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", "tranducthao243/ffdatareport"))
    parser.add_argument("--artifact-name", default=os.getenv("DATAMASTER_ARTIFACT_NAME", "ffvn-daily-fetch-latest"))
    parser.add_argument("--artifact-token", default=os.getenv("GITHUB_TOKEN", "").strip())
    parser.add_argument("--sync-on-start", action="store_true", default=_env_flag("DATAMASTER_SYNC_ON_START"))
    parser.add_argument("--sync-on-click", action="store_true", default=_env_flag("DATAMASTER_SYNC_ON_CLICK"))
    parser.add_argument("--verify-signature", action="store_true", default=_env_flag("SEATALK_VERIFY_SIGNATURE"))
    parser.add_argument("--signing-secret", default=os.getenv("SEATALK_SIGNING_SECRET", ""))
    parser.add_argument("--debug", action="store_true")
    return parser


def configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def verify_signature(raw_body: bytes, signing_secret: str, received_signature: str) -> bool:
    if not signing_secret or not received_signature:
        return False
    expected = hashlib.sha256(raw_body + signing_secret.encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, received_signature)


def build_runtime(args: argparse.Namespace) -> dict[str, Any]:
    preset = load_preset(args.preset)
    preset_data = preset.data
    admin_codes: list[str] = []
    for raw in (os.getenv("SEATALK_ADMIN_EMPLOYEE_CODES", ""), os.getenv("SEATALK_ADMIN_EMPLOYEE_CODE", "")):
        for token in raw.replace(";", ",").split(","):
            value = token.strip()
            if value and value not in admin_codes:
                admin_codes.append(value)
    admin_emails: list[str] = []
    for raw in (os.getenv("SEATALK_ADMIN_EMAILS", ""), os.getenv("SEATALK_ADMIN_EMAIL", "")):
        for token in raw.replace(";", ",").split(","):
            value = token.strip().lower()
            if value and value not in admin_emails:
                admin_emails.append(value)
    admin_seatalk_ids: list[str] = []
    for raw in (os.getenv("SEATALK_ADMIN_SEATALK_IDS", ""), os.getenv("SEATALK_ADMIN_SEATALK_ID", "")):
        for token in raw.replace(";", ",").split(","):
            value = token.strip()
            if value and value not in admin_seatalk_ids:
                admin_seatalk_ids.append(value)
    return {
        "db_path": args.db_path,
        "groups_config": args.groups_config,
        "reports_config": args.reports_config,
        "campaigns_config": args.campaigns_config,
        "preset_category_ids": list(preset_data.get("category_ids") or []),
        "preset_platform_ids": list(preset_data.get("platform_ids") or []),
        "report_mode": args.report_mode,
        "report_timezone": args.report_timezone,
        "repo": args.repo,
        "artifact_name": args.artifact_name,
        "artifact_token": args.artifact_token,
        "sync_on_start": bool(args.sync_on_start),
        "sync_on_click": bool(args.sync_on_click),
        "verify_signature": bool(args.verify_signature),
        "signing_secret": args.signing_secret,
        "seatalk_app_id": os.getenv("SEATALK_APP_ID", "").strip(),
        "seatalk_app_secret": os.getenv("SEATALK_APP_SECRET", "").strip(),
        "admin_employee_codes": admin_codes,
        "admin_emails": admin_emails,
        "admin_seatalk_ids": admin_seatalk_ids,
        "admin_contact_email": os.getenv("SEATALK_ADMIN_CONTACT_EMAIL", "ducthao.tran@garena.vn").strip(),
    }


def sync_store_from_github_artifact(runtime: dict[str, Any]) -> bool:
    token = str(runtime.get("artifact_token") or "").strip()
    repo = str(runtime.get("repo") or "").strip()
    artifact_name = str(runtime.get("artifact_name") or "").strip()
    db_path = Path(runtime["db_path"])
    if not token or not repo or not artifact_name:
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = requests.get(
        f"https://api.github.com/repos/{repo}/actions/artifacts",
        params={"per_page": 100},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    artifacts = response.json().get("artifacts", [])
    candidates = [
        item
        for item in artifacts
        if item.get("name") == artifact_name and not item.get("expired")
    ]
    if not candidates:
        raise DatasocialError(f"No usable artifact named '{artifact_name}' found in repository '{repo}'.")
    candidates.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    artifact_id = candidates[0]["id"]

    download = requests.get(
        f"https://api.github.com/repos/{repo}/actions/artifacts/{artifact_id}/zip",
        headers=headers,
        timeout=120,
    )
    download.raise_for_status()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = Path(temp_dir) / "artifact.zip"
        zip_path.write_bytes(download.content)
        with zipfile.ZipFile(zip_path, "r") as archive:
            members = archive.namelist()
            sqlite_member = next(
                (
                    name
                    for name in members
                    if name.endswith("ffvn_master.sqlite")
                ),
                "",
            )
            if not sqlite_member:
                raise DatasocialError("Fetch artifact does not contain ffvn_master.sqlite.")
            extracted = archive.extract(sqlite_member, temp_dir)
            Path(extracted).replace(db_path)
    LOGGER.info("Synced SQLite store from GitHub artifact %s into %s", artifact_id, db_path)
    return True


def make_handler(runtime: dict[str, Any]) -> type[BaseHTTPRequestHandler]:
    private_message_lock = threading.Lock()
    handled_private_message_ids: dict[str, str] = {}
    active_uploads: set[tuple[str, str]] = set()

    class CallbackHandler(BaseHTTPRequestHandler):
        server_version = "SeatalkCallbackServer/1.0"

        def do_GET(self) -> None:
            if self.path == "/health":
                self._write_json(HTTPStatus.OK, {"status": "ok"})
                return
            self._write_json(HTTPStatus.NOT_FOUND, {"code": 404, "message": "Not found"})

        def do_POST(self) -> None:
            if self.path != "/callback":
                self._write_json(HTTPStatus.NOT_FOUND, {"code": 404, "message": "Not found"})
                return

            raw_body = self._read_body()
            if runtime["verify_signature"]:
                signature = self.headers.get("Signature") or self.headers.get("X-SeaTalk-Signature") or ""
                if not verify_signature(raw_body, runtime["signing_secret"], signature):
                    self._write_json(HTTPStatus.FORBIDDEN, {"code": 403, "message": "Invalid signature"})
                    return

            payload = self._load_json(raw_body)
            LOGGER.info("Seatalk callback payload | %s", json.dumps(payload, ensure_ascii=False, sort_keys=True))
            event_type = str(payload.get("event_type") or "").strip()
            event = payload.get("event") or {}

            try:
                if event_type == "event_verification":
                    self._write_json(HTTPStatus.OK, {"seatalk_challenge": event.get("seatalk_challenge", "")})
                    return

                if event_type == "interactive_message_click":
                    self._handle_interactive_click(event)
                    self._write_json(HTTPStatus.OK, {"code": 0})
                    return

                if event_type in {
                    "message_from_bot_subscriber",
                    "message_received_from_bot_user",
                    "message_from_user",
                }:
                    self._handle_private_message(event)
                    self._write_json(HTTPStatus.OK, {"code": 0})
                    return

                self._write_json(HTTPStatus.OK, {"code": 0})
            except Exception as exc:
                LOGGER.exception("Callback handling failed")
                self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"code": 500, "message": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            LOGGER.info("%s - %s", self.address_string(), format % args)

        def _handle_interactive_click(self, event: dict[str, Any]) -> None:
            callback_context = build_callback_context(event)
            LOGGER.info(
                "Seatalk callback context | %s",
                json.dumps(callback_context, ensure_ascii=False, sort_keys=True),
            )
            employee_code = callback_context["employee_code"]
            group_id = callback_context["group_id"]
            thread_id = callback_context["thread_id"] or callback_context["message_id"]
            quoted_message_id = callback_context["message_id"] or callback_context["quoted_message_id"]
            if not employee_code:
                raise SeatalkCallbackError("Missing employee_code in callback event.")
            if not runtime["seatalk_app_id"] or not runtime["seatalk_app_secret"]:
                raise SeatalkCallbackError(
                    "SEATALK_APP_ID and SEATALK_APP_SECRET are required before callback replies can be sent."
                )
            raw_value = extract_click_value(event)
            click_payload = parse_click_payload(raw_value)
            action = str(click_payload.get("action") or "").strip()
            if action not in {"open_report", "reply_text"}:
                raise SeatalkCallbackError(f"Unsupported interactive action: {action or '-'}")

            private_client = build_seatalk_client(
                app_id=runtime["seatalk_app_id"],
                app_secret=runtime["seatalk_app_secret"],
                employee_code=employee_code,
                thread_id=thread_id,
            )
            if not _is_authorized_private_sender(runtime, callback_context):
                private_client.send_text(
                    _format_private_access_denied(
                        callback_context,
                        contact_email=runtime["admin_contact_email"],
                    )
                )
                LOGGER.info(
                    "Rejected interactive private delivery for unauthorized sender | employee_code=%s | email=%s | seatalk_id=%s",
                    callback_context["employee_code"],
                    callback_context["email"] or "-",
                    callback_context["seatalk_id"] or "-",
                )
                return

            target_report_code = str(click_payload.get("target_report_code") or "").strip()
            if action == "open_report" and not target_report_code:
                raise SeatalkCallbackError("Missing target_report_code in callback payload.")
            try:
                typing_client = build_seatalk_client(
                    app_id=runtime["seatalk_app_id"],
                    app_secret=runtime["seatalk_app_secret"],
                    employee_code=employee_code,
                    thread_id=thread_id,
                )
                typing_client.set_typing_status()
                LOGGER.info(
                    "Seatalk typing status sent | employee_code=%s | group_id=%s | thread_id=%s",
                    employee_code or "-",
                    group_id or "-",
                    thread_id or "-",
                )
            except Exception:
                LOGGER.exception(
                    "Seatalk typing status failed | employee_code=%s | group_id=%s | thread_id=%s",
                    employee_code or "-",
                    group_id or "-",
                    thread_id or "-",
                )
            if runtime["sync_on_click"]:
                sync_store_from_github_artifact(runtime)

            if action == "reply_text":
                message_text = str(click_payload.get("message") or "").strip()
                if not message_text:
                    message_text = TREND_PLACEHOLDER_MESSAGES.get(
                        target_report_code,
                        (
                            "**Thông tin đang được cập nhật**\n"
                            "*Tôi sẽ mở nội dung này ngay khi dữ liệu sẵn sàng.*"
                        ),
                    )
            else:
                package = build_report_package_by_code(
                    runtime["db_path"],
                    report_code=target_report_code,
                    groups_path=runtime["groups_config"],
                    reports_path=runtime["reports_config"],
                    campaigns_path=runtime["campaigns_config"],
                    timezone_name=runtime["report_timezone"],
                    mode=runtime["report_mode"],
                    source_scope={
                        "category_ids": runtime["preset_category_ids"],
                        "platform_ids": runtime["preset_platform_ids"],
                    },
                    now=datetime.now(),
                )
                message_text = str(package.get("renderedText") or "").strip()

            private_client.send_text(message_text)
            LOGGER.info(
                "Seatalk callback reply sent as private message | employee_code=%s | from_group=%s",
                employee_code,
                group_id or "-",
            )

        def _handle_private_message(self, event: dict[str, Any]) -> None:
            callback_context = build_callback_context(event)
            LOGGER.info(
                "Seatalk private message context | %s",
                json.dumps(callback_context, ensure_ascii=False, sort_keys=True),
            )
            employee_code = callback_context["employee_code"]
            if not employee_code:
                raise SeatalkCallbackError("Missing employee_code in private message event.")
            if not _is_authorized_private_sender(runtime, callback_context):
                client = build_seatalk_client(
                    app_id=runtime["seatalk_app_id"],
                    app_secret=runtime["seatalk_app_secret"],
                    employee_code=employee_code,
                )
                client.send_text(
                    _format_private_access_denied(
                        callback_context,
                        contact_email=runtime["admin_contact_email"],
                    )
                )
                LOGGER.info(
                    "Rejected private command from unauthorized sender | employee_code=%s | email=%s | seatalk_id=%s",
                    callback_context["employee_code"],
                    callback_context["email"] or "-",
                    callback_context["seatalk_id"] or "-",
                )
                return

            if callback_context.get("message_tag") == "image":
                self._handle_private_image_message(callback_context)
                return

            message_text = callback_context["message_text"]
            command = classify_private_command(message_text)
            message_id = callback_context.get("message_id", "")
            if command in {"uploadimage", "removebg"} and message_id:
                with private_message_lock:
                    if message_id in handled_private_message_ids:
                        LOGGER.info(
                            "Skipping duplicate private image command callback | employee_code=%s | message_id=%s | command=%s",
                            employee_code,
                            message_id,
                            command,
                        )
                        return
                    handled_private_message_ids[message_id] = employee_code
            thread_id = callback_context["thread_id"] or callback_context["message_id"]
            private_client = build_seatalk_client(
                app_id=runtime["seatalk_app_id"],
                app_secret=runtime["seatalk_app_secret"],
                employee_code=employee_code,
                thread_id=thread_id,
            )
            try:
                private_client.set_typing_status()
                LOGGER.info(
                    "Seatalk private typing status sent | employee_code=%s | thread_id=%s",
                    employee_code,
                    thread_id or "-",
                )
            except Exception:
                LOGGER.exception(
                    "Seatalk private typing status failed | employee_code=%s | thread_id=%s",
                    employee_code,
                    thread_id or "-",
                )

            campaigns_config = load_json(runtime["campaigns_config"])
            reports_payload = self._build_reports_payload()
            health_snapshot = build_health_snapshot(
                reports_payload,
                db_path=runtime["db_path"],
                source_scope={
                    "category_ids": runtime["preset_category_ids"],
                    "platform_ids": runtime["preset_platform_ids"],
                },
                campaigns_config=campaigns_config,
                now=datetime.now(),
            )

            if command == "campaign":
                reply_text = self._build_report_text("TOPD_REPORT")
            elif command == "official":
                reply_text = self._build_report_text("TOPF_REPORT")
            elif command == "dance":
                reply_text = self._build_report_text("TOPG_REPORT")
            elif command == "roblox":
                reply_text = self._build_report_text("TOPH_REPORT")
            elif command == "data":
                reply_text = format_data_report(health_snapshot)
            elif command == "scope":
                reply_text = format_scope_report(health_snapshot)
            elif command == "health":
                reply_text = format_health_report(health_snapshot)
            elif command == "web":
                links_payload = load_json(Path("config/webcompany_links.json"))
                lines = ["**Link web quan trọng của team**"]
                sections = links_payload.get("sections") or []
                if not sections and links_payload.get("links"):
                    sections = [{"title": "Link tổng hợp", "links": links_payload.get("links") or []}]
                if not sections:
                    lines.append("- Chưa cấu hình link nào.")
                else:
                    for section in sections:
                        lines.append(f"\n**{section.get('title', 'Danh sách link')}**")
                        for item in section.get("links") or []:
                            lines.append(f"- {item.get('label', 'Link')}: {item.get('url', '-')}")
                            if item.get("note"):
                                lines.append(f"  *{item['note']}*")
                reply_text = "\n".join(lines)
            elif command == "hashtag":
                reply_text = format_hashtag_report(runtime["db_path"], message_text)
            elif command == "uploadimage":
                reply_text = self._handle_uploadimage_command(callback_context)
            elif command == "removebg":
                reply_text = self._handle_removebg_command(callback_context)
            elif command in {"shortlink", "enhanceimage"}:
                reply_text = PRIVATE_FUTURE_FEATURE_MESSAGE
            elif command == "help":
                reply_text = (
                    "**LỆNH BOT PRIVATE**\n"
                    "*Gõ `.` để mở nhanh menu này.*\n"
                    "\n"
                    "**Kiểm tra dữ liệu**\n"
                    "- `health`: tổng quan tình trạng dữ liệu\n"
                    "- `data`: kho dữ liệu đang dùng\n"
                    "- `scope`: source scope hiện tại\n"
                    "\n"
                    "**Tiện ích**\n"
                    "- `web`: liệt kê các link web quan trọng của team\n"
                    "- `hashtag`: gõ hashtag và tên hashtag để check data\n"
                    "\n"
                    "**Dữ liệu KOLs**\n"
                    "- `campaign`: báo cáo campaign hiện tại\n"
                    "- `official`: báo cáo kênh Official\n"
                    "- `dance`: báo cáo video trend nhảy\n"
                    "- `roblox`: báo cáo TOP video Roblox\n"
                    "\n"
                    "**Tính năng sắp cập nhật**\n"
                    "- `shortlink`: tạo shortlink từ link và config\n"
                    "- `uploadimage`: tải ảnh lên web nội bộ và trả link ảnh\n"
                    "- `enhanceimage`: làm nét ảnh rồi trả kết quả\n"
                    "- `removebg`: tách nền ảnh và trả lại ảnh\n"
                    "\n"
                    "**Hướng dẫn**\n"
                    "- `help`: xem menu này và cách dùng bot\n"
                )
            else:
                reply_text = answer_data_question(
                    runtime["db_path"],
                    message_text,
                    now=datetime.now(),
                ) or (
                    "**Tôi chưa hiểu câu hỏi này**\n"
                    "*Thử lại bằng một lệnh như `health`, `campaign`, `official` "
                    "hoặc một câu hỏi dữ liệu cụ thể.*"
                )

            if reply_text:
                private_client.send_text(reply_text)
                LOGGER.info(
                    "Seatalk private command reply sent | employee_code=%s | command=%s",
                    employee_code,
                    command,
                )

        def _handle_private_image_message(self, callback_context: dict[str, str]) -> None:
            employee_code = callback_context["employee_code"]
            image_url = callback_context.get("image_url", "")
            if not image_url:
                raise SeatalkCallbackError("Image message missing image URL.")

            store_latest_image_for_user(
                get_image_store_path(),
                employee_code=employee_code,
                seatalk_id=callback_context.get("seatalk_id", ""),
                message_id=callback_context.get("message_id", ""),
                image_url=image_url,
                thread_id=callback_context.get("thread_id") or callback_context.get("message_id", ""),
            )

            client = build_seatalk_client(
                app_id=runtime["seatalk_app_id"],
                app_secret=runtime["seatalk_app_secret"],
                employee_code=employee_code,
                thread_id=callback_context.get("thread_id") or callback_context.get("message_id", ""),
            )
            send_seatalk_text_reply(
                client,
                (
                    "**Da nhan anh gan nhat cua ban**\n"
                    "*Go `uploadimage` de tai anh len web noi bo va nhan link ket qua.*\n"
                    "*Go `removebg` de tai anh len web tach nen va tra lai anh ket qua.*"
                ),
            )

        def _handle_uploadimage_command(self, callback_context: dict[str, str]) -> str:
            employee_code = callback_context["employee_code"]
            active_job = (employee_code, "uploadimage")
            LOGGER.info("Seatalk uploadimage command received | employee_code=%s", employee_code)
            with private_message_lock:
                if active_job in active_uploads:
                    LOGGER.info("Seatalk uploadimage already in progress | employee_code=%s", employee_code)
                    return (
                        "**Ảnh gần nhất của bạn đang được xử lý**\n"
                        "*Vui lòng chờ bot hoàn tất rồi thử lại nếu cần.*"
                    )
                active_uploads.add(active_job)

            image_entry = get_latest_unprocessed_image_for_user(
                get_image_store_path(),
                employee_code=employee_code,
                command_name="uploadimage",
            )
            if not image_entry:
                with private_message_lock:
                    active_uploads.discard(active_job)
                return (
                    "**Chưa có ảnh nào để tải lên**\n"
                    "*Hãy gửi một ảnh cho bot trước, sau đó gõ `uploadimage`.*"
                )

            try:
                image_path = download_seatalk_image(
                    image_url=str(image_entry.get("image_url") or "").strip(),
                    app_id=runtime["seatalk_app_id"],
                    app_secret=runtime["seatalk_app_secret"],
                    filename_hint=str(image_entry.get("message_id") or employee_code),
                )
            except Exception as exc:
                LOGGER.exception("Seatalk image download failure | employee_code=%s", employee_code)
                with private_message_lock:
                    active_uploads.discard(active_job)
                return (
                    "**Tải ảnh từ Seatalk thất bại**\n"
                    f"*Chi tiết: {exc}*"
                )

            try:
                final_url = upload_image_to_vendor_tool(image_path)
            except UploadImageError as exc:
                LOGGER.exception("Vendor upload flow failure | employee_code=%s", employee_code)
                with private_message_lock:
                    active_uploads.discard(active_job)
                return (
                    "**Upload ảnh lên Vendor Tool thất bại**\n"
                    f"*Chi tiết: {summarize_upload_error(exc)}*"
                )
            except Exception as exc:
                LOGGER.exception("Unexpected vendor upload failure | employee_code=%s", employee_code)
                with private_message_lock:
                    active_uploads.discard(active_job)
                return (
                    "**Upload ảnh lên Vendor Tool thất bại**\n"
                    f"*Chi tiết: {summarize_upload_error(exc)}*"
                )

            mark_image_processed_for_user(
                get_image_store_path(),
                employee_code=employee_code,
                message_id=str(image_entry.get("message_id") or ""),
                command_name="uploadimage",
            )
            with private_message_lock:
                active_uploads.discard(active_job)
            return (
                "**Upload ảnh thành công**\n"
                f"- Link ảnh: {final_url}"
            )

        def _handle_removebg_command(self, callback_context: dict[str, str]) -> str:
            employee_code = callback_context["employee_code"]
            active_job = (employee_code, "removebg")
            LOGGER.info("Seatalk removebg command received | employee_code=%s", employee_code)
            with private_message_lock:
                if active_job in active_uploads:
                    LOGGER.info("Seatalk removebg already in progress | employee_code=%s", employee_code)
                    return (
                        "**Anh gan nhat cua ban dang duoc xu ly**\n"
                        "*Vui long cho bot hoan tat roi thu lai neu can.*"
                    )
                active_uploads.add(active_job)

            image_entry = get_latest_unprocessed_image_for_user(
                get_image_store_path(),
                employee_code=employee_code,
                command_name="removebg",
            )
            if not image_entry:
                with private_message_lock:
                    active_uploads.discard(active_job)
                return (
                    "**Chua co anh nao de tach nen**\n"
                    "*Hay gui mot anh cho bot truoc, sau do go `removebg`.*"
                )

            try:
                image_path = download_seatalk_image(
                    image_url=str(image_entry.get("image_url") or "").strip(),
                    app_id=runtime["seatalk_app_id"],
                    app_secret=runtime["seatalk_app_secret"],
                    filename_hint=str(image_entry.get("message_id") or employee_code),
                )
                output_path = remove_background_with_space(image_path)

                private_client = build_seatalk_client(
                    app_id=runtime["seatalk_app_id"],
                    app_secret=runtime["seatalk_app_secret"],
                    employee_code=employee_code,
                    thread_id=callback_context.get("thread_id") or callback_context.get("message_id", ""),
                )
                send_seatalk_image_reply(private_client, output_path)
            except UploadImageError as exc:
                LOGGER.exception("Remove background flow failure | employee_code=%s", employee_code)
                with private_message_lock:
                    active_uploads.discard(active_job)
                return (
                    "**Tach nen anh that bai**\n"
                    f"*Chi tiet: {summarize_upload_error(exc)}*"
                )
            except Exception as exc:
                LOGGER.exception("Unexpected remove background failure | employee_code=%s", employee_code)
                with private_message_lock:
                    active_uploads.discard(active_job)
                return (
                    "**Tach nen anh that bai**\n"
                    f"*Chi tiet: {summarize_upload_error(exc)}*"
                )

            mark_image_processed_for_user(
                get_image_store_path(),
                employee_code=employee_code,
                message_id=str(image_entry.get("message_id") or ""),
                command_name="removebg",
            )
            with private_message_lock:
                active_uploads.discard(active_job)
            return ""

        def _build_report_text(self, report_code: str) -> str:
            package = build_report_package_by_code(
                runtime["db_path"],
                report_code=report_code,
                groups_path=runtime["groups_config"],
                reports_path=runtime["reports_config"],
                campaigns_path=runtime["campaigns_config"],
                timezone_name=runtime["report_timezone"],
                mode=runtime["report_mode"],
                source_scope={
                    "category_ids": runtime["preset_category_ids"],
                    "platform_ids": runtime["preset_platform_ids"],
                },
                now=datetime.now(),
            )
            return str(package.get("renderedText") or "").strip()

        def _build_reports_payload(self) -> dict[str, Any]:
            from app.pipeline import build_configured_reports

            return build_configured_reports(
                runtime["db_path"],
                groups_path=runtime["groups_config"],
                reports_path=runtime["reports_config"],
                campaigns_path=runtime["campaigns_config"],
                timezone_name=runtime["report_timezone"],
                mode=runtime["report_mode"],
                source_scope={
                    "category_ids": runtime["preset_category_ids"],
                    "platform_ids": runtime["preset_platform_ids"],
                },
                send=False,
                seatalk_app_id=runtime["seatalk_app_id"],
                seatalk_app_secret=runtime["seatalk_app_secret"],
                seatalk_admin_employee_codes=runtime["admin_employee_codes"],
            )

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", "0") or "0")
            return self.rfile.read(length)

        def _load_json(self, raw_body: bytes) -> dict[str, Any]:
            if not raw_body:
                return {}
            return json.loads(raw_body.decode("utf-8"))

        def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return CallbackHandler


def run_server(args: argparse.Namespace) -> None:
    configure_logging(args.debug)
    runtime = build_runtime(args)
    if not runtime["seatalk_app_id"] or not runtime["seatalk_app_secret"]:
        LOGGER.warning(
            "SEATALK_APP_ID and/or SEATALK_APP_SECRET are not configured. "
            "Server will start, but callback replies will fail until these vars are set."
        )
    if runtime["sync_on_start"]:
        sync_store_from_github_artifact(runtime)
    handler = make_handler(runtime)
    with ThreadingHTTPServer((args.host, args.port), handler) as server:
        LOGGER.info("Seatalk callback server listening on http://%s:%s", args.host, args.port)
        server.serve_forever()


def main() -> int:
    args = build_parser().parse_args()
    run_server(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


