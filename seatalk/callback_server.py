from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import tempfile
import threading
import time
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
    format_data_report,
    format_health_alert,
    format_health_report,
    format_scope_report,
    normalize_command_text,
)
from app.private_reports import format_hashtag_report_v2, format_kol_report
from datasocial.exceptions import DatasocialError
from datasocial.presets import load_preset
from datasocial.seatalk import SeaTalkError

from .auth import build_seatalk_client
from .identity import build_unified_user, get_superadmins, load_env_role_directory, load_user_directory
from .alerts import send_superadmin_alerts
from .group_thread_service import is_allowed_ctv_group as service_is_allowed_ctv_group, split_csv_env
from .interactive import build_interactive_groups, build_superadmin_control_payload
from .payloads import build_interactive_group_payload
from .private_bot_service import (
    build_private_help_text as service_build_private_help_text,
    build_private_usage_text as service_build_private_usage_text,
    format_private_access_denied as service_format_private_access_denied,
    is_authorized_private_sender as service_is_authorized_private_sender,
)
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
SEATALK_REMOVEBG_VENDOR_FALLBACK_ENABLED = os.getenv("SEATALK_REMOVEBG_VENDOR_FALLBACK_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
WORKFLOW_NAME_MAP = {
    "ffvn-daily-fetch.yml": "FFVN Daily Fetch (Scheduled)",
    "ffvn-daily-send.yml": "FFVN Daily Send (Scheduled)",
}


PRIVATE_FUTURE_FEATURE_MESSAGE = (
    "**Đang check và sẽ cập nhật tính năng sau**\n"
    "*Tính năng này đã được ghi nhận trong roadmap của bot.*"
)


def _is_authorized_private_sender(runtime: dict[str, Any], callback_context: dict[str, str]) -> bool:
    directory = runtime.get("user_directory") or []
    env_directory = runtime.get("env_role_directory") or []
    if not directory and not env_directory:
        return True
    unified_user = build_unified_user(callback_context, directory, env_directory=env_directory)
    return unified_user["role"] in {"admin", "superadmin"}


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


def _build_private_help_text(role: str) -> str:
    lines = [
        "**LỆNH BOT PRIVATE**",
        "*Gõ `.` để mở nhanh menu này.*",
        "",
    ]
    if role == "superadmin":
        lines.extend(
            [
                "**Kiểm tra dữ liệu**",
                "- `health`: tổng quan tình trạng dữ liệu",
                "- `data`: kho dữ liệu đang dùng",
                "- `scope`: source scope hiện tại",
                "",
            ]
        )
    lines.extend(
        [
            "**Tiện ích**",
            "- `web`: liệt kê các link web quan trọng của team",
            "- `hashtag`: gõ hashtag và tên hashtag để check data",
            "- `kol`: gõ `kol <tên KOL>` để check data theo KOL",
            "",
            "**Dữ liệu KOLs**",
            "- `campaign`: báo cáo campaign hiện tại",
            "- `official`: báo cáo kênh Official",
            "- `dance`: báo cáo video trend nhảy",
            "- `roblox`: báo cáo TOP video Roblox",
            "",
            "**Tính năng khác**",
            "- `imagelink`: tải ảnh lên web nội bộ và trả link ảnh",
            "- `removebg`: tách nền ảnh và trả lại ảnh",
            "- `shortlink`: tạo shortlink từ link và config",
            "- `enhanceimage`: làm nét ảnh rồi trả kết quả",
            "",
            "**Hướng dẫn**",
            "- `help`: xem menu này và cách dùng bot",
            "",
            "Bạn gõ dấu chấm `.` để gọi bảng tính năng, chỉ cần gõ lệnh là có thể gọi được dữ liệu hoặc nhờ bot giải quyết các vấn đề cần thiết. Dự kiến BOT sẽ cập nhật thêm nhiều tính năng hơn nữa. Dữ liệu từ hệ thống của Free Fire. Nếu bạn có góp ý gì vui lòng liên hệ superadmin ducthao.tran@garena.vn",
        ]
    )
    return "\n".join(lines)


def _build_private_usage_text() -> str:
    return (
        "**HƯỚNG DẪN SỬ DỤNG BOT**\n"
        "Bạn gõ dấu chấm `.` để gọi bảng tính năng, chỉ cần gõ lệnh là có thể gọi được dữ liệu hoặc nhờ bot giải quyết các vấn đề cần thiết. "
        "Dự kiến BOT sẽ cập nhật thêm nhiều tính năng hơn nữa. Dữ liệu từ hệ thống của Free Fire. "
        "Nếu bạn có góp ý gì vui lòng liên hệ superadmin ducthao.tran@garena.vn"
    )


def _is_allowed_ctv_group(runtime: dict[str, Any], callback_context: dict[str, str]) -> bool:
    group_id = str(callback_context.get("group_id") or "").strip()
    return bool(group_id and group_id in set(runtime.get("ctv_group_ids") or []))


def _message_addresses_bot(runtime: dict[str, Any], message_text: str) -> bool:
    normalized = normalize_command_text(message_text)
    if not normalized:
        return False
    for alias in runtime.get("group_bot_aliases") or []:
        if alias and alias in normalized:
            return True
    return False


def _strip_group_bot_aliases(runtime: dict[str, Any], message_text: str) -> str:
    cleaned = str(message_text or "")
    for alias in runtime.get("group_bot_aliases") or []:
        if not alias:
            continue
        cleaned = re.sub(re.escape(alias), " ", normalize_command_text(cleaned), flags=re.IGNORECASE)
        break
    return " ".join(cleaned.split()).strip()


def _build_private_help_text(role: str) -> str:
    lines = [
        "**LỆNH BOT PRIVATE**",
        "*Gõ `.` để mở nhanh menu này.*",
        "",
    ]
    if role == "superadmin":
        lines.extend(
            [
                "**Kiểm tra dữ liệu**",
                "- `health`: tổng quan tình trạng dữ liệu",
                "- `data`: kho dữ liệu đang dùng",
                "- `scope`: source scope hiện tại",
                "",
            ]
        )
    lines.extend(
        [
            "**Tiện ích**",
            "- `web`: liệt kê các link web quan trọng của team",
            "- `hashtag`: gõ hashtag và tên hashtag để check data",
            "- `kol`: gõ `kol <tên KOL>` để check data theo KOL",
            "",
            "**Dữ liệu KOLs**",
            "- `campaign`: báo cáo campaign hiện tại",
            "- `official`: báo cáo kênh Official",
            "- `dance`: báo cáo video trend nhảy",
            "- `roblox`: báo cáo TOP video Roblox",
            "",
            "**Tính năng khác**",
            "- `imagelink`: tải ảnh lên web nội bộ và trả link ảnh",
            "- `removebg`: tách nền ảnh và trả lại ảnh",
            "- `shortlink`: tạo shortlink từ link và config",
            "- `enhanceimage`: làm nét ảnh rồi trả kết quả",
            "",
            "**Hướng dẫn**",
            "- `help`: xem cách dùng bot",
        ]
    )
    return "\n".join(lines)


def _build_private_usage_text() -> str:
    return (
        "**HƯỚNG DẪN SỬ DỤNG BOT**\n"
        "\n"
        "- Gõ dấu chấm `.` để gọi bảng tính năng.\n"
        "- Chỉ cần gõ lệnh là có thể gọi được dữ liệu hoặc nhờ bot giải quyết các vấn đề cần thiết.\n"
        "- Dự kiến BOT sẽ cập nhật thêm nhiều tính năng hơn nữa.\n"
        "- Dữ liệu từ hệ thống của Free Fire.\n"
        "- Nếu bạn có góp ý gì vui lòng liên hệ superadmin `ducthao.tran@garena.vn`."
    )


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _split_csv_env(*values: str) -> list[str]:
    items: list[str] = []
    for raw in values:
        for token in str(raw or "").replace(";", ",").split(","):
            value = token.strip()
            if value and value not in items:
                items.append(value)
    return items


def _normalize_alias(alias: str) -> str:
    return normalize_command_text(alias).replace("@", "").strip()


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
    user_directory = load_user_directory(Path(os.getenv("SEATALK_USERS_CONFIG", "config/users.json")))
    env_role_directory = load_env_role_directory()
    superadmin_users = get_superadmins(env_role_directory) or get_superadmins(user_directory)
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
        "github_ref": os.getenv("GITHUB_REF_NAME", "main").strip() or "main",
        "artifact_name": args.artifact_name,
        "artifact_token": args.artifact_token,
        "sync_on_start": bool(args.sync_on_start),
        "sync_on_click": bool(args.sync_on_click),
        "verify_signature": bool(args.verify_signature),
        "signing_secret": args.signing_secret,
        "seatalk_app_id": os.getenv("SEATALK_APP_ID", "").strip(),
        "seatalk_app_secret": os.getenv("SEATALK_APP_SECRET", "").strip(),
        "admin_contact_email": os.getenv("SEATALK_ADMIN_CONTACT_EMAIL", "ducthao.tran@garena.vn").strip(),
        "user_directory": user_directory,
        "env_role_directory": env_role_directory,
        "superadmin_users": superadmin_users,
        "kol_mapping_path": Path(os.getenv("SEATALK_KOL_MAPPING_PATH", "config/kol_channels.json")),
        "ctv_group_ids": split_csv_env(os.getenv("SEATALK_CTV_GROUP_IDS", "")),
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


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def trigger_github_workflow(runtime: dict[str, Any], *, workflow_file: str, inputs: dict[str, Any] | None = None) -> None:
    token = str(runtime.get("artifact_token") or "").strip()
    repo = str(runtime.get("repo") or "").strip()
    ref = str(runtime.get("github_ref") or "main").strip() or "main"
    if not token or not repo:
        raise DatasocialError("GitHub workflow trigger chưa được cấu hình đủ token/repo.")

    response = requests.post(
        f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/dispatches",
        headers=_github_headers(token),
        json={"ref": ref, "inputs": inputs or {}},
        timeout=30,
    )
    if response.status_code not in {200, 201, 204}:
        raise DatasocialError(
            f"GitHub workflow dispatch failed with HTTP {response.status_code}: {response.text[:500]}"
        )


def wait_for_github_workflow_completion(
    runtime: dict[str, Any],
    *,
    workflow_file: str,
    started_after: datetime,
    timeout_seconds: int = 1800,
    poll_interval_seconds: int = 15,
) -> dict[str, Any]:
    token = str(runtime.get("artifact_token") or "").strip()
    repo = str(runtime.get("repo") or "").strip()
    if not token or not repo:
        raise DatasocialError("GitHub workflow polling chưa được cấu hình đủ token/repo.")

    deadline = time.time() + timeout_seconds
    matched_run_id = None
    matched_run: dict[str, Any] | None = None
    while time.time() < deadline:
        response = requests.get(
            f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/runs",
            headers=_github_headers(token),
            params={"event": "workflow_dispatch", "per_page": 10},
            timeout=30,
        )
        response.raise_for_status()
        runs = response.json().get("workflow_runs", [])
        for run in runs:
            created_at = str(run.get("created_at") or "").strip()
            if not created_at:
                continue
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
            if created_dt < started_after:
                continue
            matched_run_id = run.get("id")
            matched_run = run
            break

        if matched_run_id is not None:
            status = str(matched_run.get("status") or "").strip().lower()
            if status == "completed":
                return matched_run or {}
        time.sleep(poll_interval_seconds)

    raise DatasocialError(
        f"Timed out waiting for workflow {workflow_file} to complete after dispatch."
    )


def notify_superadmins_workflow_result(
    runtime: dict[str, Any],
    *,
    workflow_file: str,
    run: dict[str, Any],
) -> None:
    if not runtime.get("superadmin_users"):
        return
    workflow_name = WORKFLOW_NAME_MAP.get(workflow_file, workflow_file)
    conclusion = str(run.get("conclusion") or "-").strip()
    html_url = str(run.get("html_url") or "").strip()
    body = (
        f"Workflow: {workflow_name}\n"
        f"Status: {conclusion}\n"
        f"Run ID: {run.get('id') or '-'}"
    )
    if html_url:
        body += f"\nLink: {html_url}"
    send_superadmin_alerts(
        app_id=runtime["seatalk_app_id"],
        app_secret=runtime["seatalk_app_secret"],
        superadmins=runtime["superadmin_users"],
        title="GitHub workflow completed",
        body=body,
    )


def start_workflow_monitor(runtime: dict[str, Any], *, workflow_file: str, started_after: datetime) -> None:
    def _runner() -> None:
        try:
            run = wait_for_github_workflow_completion(
                runtime,
                workflow_file=workflow_file,
                started_after=started_after,
            )
            notify_superadmins_workflow_result(runtime, workflow_file=workflow_file, run=run)
        except Exception as exc:
            LOGGER.exception("Workflow monitor failed | workflow=%s", workflow_file)
            if runtime.get("superadmin_users"):
                send_superadmin_alerts(
                    app_id=runtime["seatalk_app_id"],
                    app_secret=runtime["seatalk_app_secret"],
                    superadmins=runtime["superadmin_users"],
                    title="GitHub workflow monitoring failed",
                    body=f"Workflow: {WORKFLOW_NAME_MAP.get(workflow_file, workflow_file)}\nError: {type(exc).__name__}: {exc}",
                )

    thread = threading.Thread(target=_runner, daemon=True, name=f"workflow-monitor-{workflow_file}")
    thread.start()


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
                    callback_context = build_callback_context(event)
                    if callback_context.get("group_id"):
                        self._handle_group_message(event)
                    else:
                        self._handle_private_message(event)
                    self._write_json(HTTPStatus.OK, {"code": 0})
                    return

                self._write_json(HTTPStatus.OK, {"code": 0})
            except Exception as exc:
                LOGGER.exception("Callback handling failed")
                self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"code": 500, "message": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            LOGGER.info("%s - %s", self.address_string(), format % args)

        def _notify_superadmins_once(self, key: str, title: str, body: str) -> None:
            if not key or not runtime.get("superadmin_users"):
                return
            with private_message_lock:
                sent_alert_keys: set[str] = getattr(self.server, "_sent_alert_keys", set())
                if key in sent_alert_keys:
                    return
                sent_alert_keys.add(key)
                setattr(self.server, "_sent_alert_keys", sent_alert_keys)
            try:
                results = send_superadmin_alerts(
                    app_id=runtime["seatalk_app_id"],
                    app_secret=runtime["seatalk_app_secret"],
                    superadmins=runtime["superadmin_users"],
                    title=title,
                    body=body,
                )
                LOGGER.info("Seatalk superadmin alert sent | key=%s | results=%s", key, json.dumps(results, ensure_ascii=False))
            except Exception:
                LOGGER.exception("Seatalk superadmin alert failed | key=%s", key)

        def _sync_store_if_needed(self, source: str) -> None:
            if not runtime["sync_on_click"]:
                return
            try:
                sync_store_from_github_artifact(runtime)
            except Exception as exc:
                self._notify_superadmins_once(
                    f"sync:{source}:{type(exc).__name__}:{exc}",
                    "Lỗi đồng bộ dữ liệu",
                    f"Nguồn: {source}\nLỗi: {type(exc).__name__}: {exc}",
                )
                raise

        def _maybe_alert_health_issues(self, health_snapshot: dict[str, Any], source: str) -> None:
            issues = health_snapshot.get("issues") or []
            if not issues:
                return
            issue_codes = ",".join(sorted(str(item.get("code") or "-") for item in issues))
            generated_at = str(health_snapshot.get("generatedAt") or "")
            self._notify_superadmins_once(
                f"health:{source}:{issue_codes}:{generated_at}",
                "Cảnh báo thiếu dữ liệu / lỗi dữ liệu",
                format_health_alert(health_snapshot),
            )

        def _build_group_client(self, callback_context: dict[str, str]):
            return build_seatalk_client(
                app_id=runtime["seatalk_app_id"],
                app_secret=runtime["seatalk_app_secret"],
                group_id=callback_context.get("group_id", ""),
                thread_id=callback_context.get("thread_id") or callback_context.get("message_id", ""),
                quoted_message_id=callback_context.get("message_id", ""),
            )

        def _build_health_snapshot(self) -> dict[str, Any]:
            campaigns_config = load_json(runtime["campaigns_config"])
            reports_payload = self._build_reports_payload()
            return build_health_snapshot(
                reports_payload,
                db_path=runtime["db_path"],
                source_scope={
                    "category_ids": runtime["preset_category_ids"],
                    "platform_ids": runtime["preset_platform_ids"],
                },
                campaigns_config=campaigns_config,
                now=datetime.now(),
            )

        def _handle_interactive_click(self, event: dict[str, Any]) -> None:
            callback_context = build_callback_context(event)
            unified_user = build_unified_user(
                callback_context,
                runtime.get("user_directory") or [],
                env_directory=runtime.get("env_role_directory") or [],
            )
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
            if action not in {"open_report", "reply_text", "trigger_workflow"}:
                raise SeatalkCallbackError(f"Unsupported interactive action: {action or '-'}")

            private_client = build_seatalk_client(
                app_id=runtime["seatalk_app_id"],
                app_secret=runtime["seatalk_app_secret"],
                employee_code=employee_code,
                thread_id=thread_id,
            )
            if not service_is_authorized_private_sender(runtime, callback_context):
                private_client.send_text(
                    service_format_private_access_denied(
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
            self._sync_store_if_needed("interactive_click")

            if action == "trigger_workflow":
                if unified_user.get("role") != "superadmin":
                    private_client.send_text("**Bạn không có quyền dùng Điều Khiển Trung Tâm.**")
                    return
                workflow_file = str(click_payload.get("workflow") or "").strip()
                if workflow_file not in WORKFLOW_NAME_MAP:
                    raise SeatalkCallbackError(f"Unsupported workflow: {workflow_file or '-'}")
                inputs = {"send_mode": "send"} if workflow_file == "ffvn-daily-send.yml" else {}
                try:
                    started_after = datetime.utcnow()
                    trigger_github_workflow(runtime, workflow_file=workflow_file, inputs=inputs)
                    start_workflow_monitor(runtime, workflow_file=workflow_file, started_after=started_after)
                    private_client.send_text(
                        f"**Đã kích hoạt {WORKFLOW_NAME_MAP[workflow_file]}**\n"
                        "*Khi workflow chạy xong, tôi sẽ gửi thông báo kết quả về cho superadmin.*"
                    )
                except Exception as exc:
                    private_client.send_text(
                        f"**Kích hoạt workflow thất bại**\n*Chi tiết: {type(exc).__name__}: {exc}*"
                    )
            elif action == "reply_text":
                message_text = str(click_payload.get("message") or "").strip()
                if not message_text:
                    message_text = TREND_PLACEHOLDER_MESSAGES.get(
                        target_report_code,
                        (
                            "**Thông tin đang được cập nhật**\n"
                            "*Tôi sẽ mở nội dung này ngay khi dữ liệu sẵn sàng.*"
                        ),
                    )
                private_client.send_text(message_text)
            else:
                self._send_private_report_with_optional_chart(private_client, target_report_code)
            LOGGER.info(
                "Seatalk callback reply sent as private message | employee_code=%s | from_group=%s",
                employee_code,
                group_id or "-",
            )

        def _handle_group_message(self, event: dict[str, Any]) -> None:
            callback_context = build_callback_context(event)
            LOGGER.info(
                "Seatalk group message context | %s",
                json.dumps(callback_context, ensure_ascii=False, sort_keys=True),
            )
            if not service_is_allowed_ctv_group(runtime, callback_context):
                LOGGER.info(
                    "Ignoring group message outside CTV allowlist | group_id=%s | employee_code=%s",
                    callback_context.get("group_id") or "-",
                    callback_context.get("employee_code") or "-",
                )
                return

            message_text = callback_context.get("message_text", "")

            if callback_context.get("message_tag") == "image":
                self._handle_group_image_message(callback_context)
                return

            callback_context = {**callback_context, "message_text": message_text}
            command = classify_private_command(message_text)
            is_menu_shortcut = normalize_command_text(message_text) == "."

            group_client = self._build_group_client(callback_context)
            try:
                group_client.set_typing_status()
            except Exception:
                LOGGER.exception(
                    "Seatalk group typing status failed | group_id=%s | thread_id=%s",
                    callback_context.get("group_id") or "-",
                    callback_context.get("thread_id") or callback_context.get("message_id") or "-",
                )

            self._sync_store_if_needed("group_message")
            health_snapshot = self._build_health_snapshot()
            self._maybe_alert_health_issues(health_snapshot, "group_message")

            if command == "campaign":
                self._send_thread_report_with_optional_chart(group_client, "TOPD_REPORT")
                return
            if command == "official":
                self._send_thread_report_with_optional_chart(group_client, "TOPF_REPORT")
                return
            if command == "roblox":
                self._send_thread_report_with_optional_chart(group_client, "TOPH_REPORT")
                return
            if command == "dance":
                reply_text = self._build_report_text("TOPG_REPORT")
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
                reply_text = format_hashtag_report_v2(runtime["db_path"], message_text, now=datetime.now())
            elif command == "kol":
                reply_text = format_kol_report(
                    runtime["db_path"],
                    message_text,
                    mapping_path=runtime["kol_mapping_path"],
                    now=datetime.now(),
                )
            elif command == "imagelink":
                group_client.send_text("**Imagelink đang chạy**\n*Tôi đang tải ảnh lên web nội bộ, vui lòng chờ một chút...*")
                reply_text = self._handle_uploadimage_command(callback_context)
            elif command == "removebg":
                group_client.send_text("**Removebg đang chạy**\n*Tôi đang tách nền ảnh, vui lòng chờ một chút...*")
                reply_text = self._handle_removebg_command(callback_context)
            elif command in {"shortlink", "enhanceimage"}:
                reply_text = PRIVATE_FUTURE_FEATURE_MESSAGE
            elif is_menu_shortcut:
                reply_text = service_build_private_help_text("admin")
            elif command == "help":
                reply_text = service_build_private_usage_text()
            else:
                reply_text = answer_data_question(
                    runtime["db_path"],
                    message_text,
                    now=datetime.now(),
                ) or (
                    "**Tôi chưa hiểu câu hỏi này**\n"
                    "*Trong group CTV, hãy tag bot để mở thread rồi tiếp tục gõ lệnh như `campaign`, `official`, `kol <tên KOL>`, `hashtag <tên hashtag>`.*"
                )

            if reply_text:
                group_client.send_text(reply_text)

        def _handle_group_image_message(self, callback_context: dict[str, str]) -> None:
            employee_code = callback_context["employee_code"]
            image_url = callback_context.get("image_url", "")
            if not employee_code or not image_url:
                return
            store_latest_image_for_user(
                get_image_store_path(),
                employee_code=employee_code,
                seatalk_id=callback_context.get("seatalk_id", ""),
                message_id=callback_context.get("message_id", ""),
                image_url=image_url,
                thread_id=callback_context.get("thread_id") or callback_context.get("message_id", ""),
            )
            self._build_group_client(callback_context).send_text(
                "Đã nhận ảnh gần nhất của bạn trong luồng này.\nGõ `imagelink` để tải ảnh lên web nội bộ.\nGõ `removebg` để tách nền ảnh."
            )

        def _handle_private_message(self, event: dict[str, Any]) -> None:
            callback_context = build_callback_context(event)
            LOGGER.info(
                "Seatalk private message context | %s",
                json.dumps(callback_context, ensure_ascii=False, sort_keys=True),
            )
            unified_user = build_unified_user(
                callback_context,
                runtime.get("user_directory") or [],
                env_directory=runtime.get("env_role_directory") or [],
            )
            LOGGER.info(
                "Seatalk unified user | %s",
                json.dumps(
                    unified_user,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            employee_code = callback_context["employee_code"]
            if not employee_code:
                raise SeatalkCallbackError("Missing employee_code in private message event.")
            if not service_is_authorized_private_sender(runtime, callback_context):
                client = build_seatalk_client(
                    app_id=runtime["seatalk_app_id"],
                    app_secret=runtime["seatalk_app_secret"],
                    employee_code=employee_code,
                )
                client.send_text(
                    service_format_private_access_denied(
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
            normalized_message_text = normalize_command_text(message_text)
            command = classify_private_command(message_text)
            is_menu_shortcut = normalized_message_text == "."
            message_id = callback_context.get("message_id", "")
            if command in {"imagelink", "removebg"} and message_id:
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

            self._sync_store_if_needed("private_message")
            health_snapshot = self._build_health_snapshot()
            self._maybe_alert_health_issues(health_snapshot, "private_message")

            if command == "campaign":
                self._send_private_report_with_optional_chart(private_client, "TOPD_REPORT")
                return
            elif command == "official":
                self._send_private_report_with_optional_chart(private_client, "TOPF_REPORT")
                return
            elif command == "so1":
                if unified_user.get("role") != "superadmin":
                    reply_text = "**Bạn không có quyền dùng lệnh `so1`.**"
                else:
                    self._send_private_report_with_interactions(private_client, "SO1")
                    return
            elif command == "chart":
                self._send_private_chart_bundle(private_client)
                return
            elif command == "dance":
                reply_text = self._build_report_text("TOPG_REPORT")
            elif command == "roblox":
                self._send_private_report_with_optional_chart(private_client, "TOPH_REPORT")
                return
            elif command == "data":
                reply_text = format_data_report(health_snapshot)
            elif command == "scope":
                reply_text = format_scope_report(health_snapshot)
            elif command == "health":
                reply_text = format_health_report(health_snapshot)
            elif command in {"fetch", "send"}:
                if unified_user.get("role") != "superadmin":
                    reply_text = "**Bạn không có quyền dùng Điều Khiển Trung Tâm.**"
                else:
                    workflow_file = "ffvn-daily-fetch.yml" if command == "fetch" else "ffvn-daily-send.yml"
                    inputs = {"send_mode": "send"} if workflow_file == "ffvn-daily-send.yml" else {}
                    try:
                        started_after = datetime.utcnow()
                        trigger_github_workflow(runtime, workflow_file=workflow_file, inputs=inputs)
                        start_workflow_monitor(runtime, workflow_file=workflow_file, started_after=started_after)
                        reply_text = (
                            f"**Đã kích hoạt {WORKFLOW_NAME_MAP[workflow_file]}**\n"
                            "*Khi workflow chạy xong, tôi sẽ gửi thông báo kết quả về cho superadmin.*"
                        )
                    except Exception as exc:
                        reply_text = f"**Kích hoạt workflow thất bại**\n*Chi tiết: {type(exc).__name__}: {exc}*"
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
                reply_text = format_hashtag_report_v2(runtime["db_path"], message_text, now=datetime.now())
            elif command == "kol":
                reply_text = format_kol_report(
                    runtime["db_path"],
                    message_text,
                    mapping_path=runtime["kol_mapping_path"],
                    now=datetime.now(),
                )
            elif command == "imagelink":
                private_client.send_text("**Imagelink đang chạy**\n*Tôi đang tải ảnh lên web nội bộ, vui lòng chờ một chút...*")
                reply_text = self._handle_uploadimage_command(callback_context)
            elif command == "removebg":
                private_client.send_text("**Removebg đang chạy**\n*Tôi đang tách nền ảnh, vui lòng chờ một chút...*")
                reply_text = self._handle_removebg_command(callback_context)
            elif command in {"shortlink", "enhanceimage"}:
                reply_text = PRIVATE_FUTURE_FEATURE_MESSAGE
            elif is_menu_shortcut:
                reply_text = service_build_private_help_text(unified_user.get("role", "admin"))
            elif command == "help":
                reply_text = service_build_private_usage_text()
            else:
                reply_text = answer_data_question(
                    runtime["db_path"],
                    message_text,
                    now=datetime.now(),
                ) or (
                    "**Tôi chưa hiểu câu hỏi này**\n"
                    "*Thử lại bằng một lệnh như `health`, `campaign`, `official`, `kol <tên KOL>` "
                    "hoặc một câu hỏi dữ liệu cụ thể.*"
                )

            if reply_text:
                private_client.send_text(reply_text)
                if is_menu_shortcut and unified_user.get("role") == "superadmin":
                    private_client.send_interactive(build_superadmin_control_payload())
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
                "Đã nhận ảnh gần nhất của bạn.\nGõ 'imagelink' để tải ảnh lên web nội bộ.\nGõ 'removebg' để tách nền ảnh.",
            )

        def _handle_uploadimage_command(self, callback_context: dict[str, str]) -> str:
            employee_code = callback_context["employee_code"]
            active_job = (employee_code, "uploadimage")
            LOGGER.info("Seatalk imagelink command received | employee_code=%s", employee_code)
            with private_message_lock:
                if active_job in active_uploads:
                    LOGGER.info("Seatalk imagelink already in progress | employee_code=%s", employee_code)
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
                    "*Hãy gửi một ảnh cho bot trước, sau đó gõ `imagelink`.*"
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
                final_url = upload_image_to_vendor_tool(
                    image_path,
                    owner_email=callback_context.get("email", ""),
                    upload_filename_hint=f"seatalk-{employee_code}-{int(datetime.now().timestamp())}",
                )
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
            return final_url

        def _handle_removebg_command(self, callback_context: dict[str, str]) -> str:
            employee_code = callback_context["employee_code"]
            active_job = (employee_code, "removebg")
            is_group_flow = bool(callback_context.get("group_id"))
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
                    "**Chưa có ảnh nào để tách nền**\n"
                    "*Hãy gửi một ảnh cho bot trước, sau đó gõ `removebg`.*"
                )

            try:
                image_path = download_seatalk_image(
                    image_url=str(image_entry.get("image_url") or "").strip(),
                    app_id=runtime["seatalk_app_id"],
                    app_secret=runtime["seatalk_app_secret"],
                    filename_hint=str(image_entry.get("message_id") or employee_code),
                )
                output_path = remove_background_with_space(image_path)
                fallback_reply = ""

                delivery_client = (
                    self._build_group_client(callback_context)
                    if is_group_flow
                    else build_seatalk_client(
                        app_id=runtime["seatalk_app_id"],
                        app_secret=runtime["seatalk_app_secret"],
                        employee_code=employee_code,
                        thread_id=callback_context.get("thread_id") or callback_context.get("message_id", ""),
                    )
                )
                try:
                    send_seatalk_image_reply(delivery_client, output_path)
                except SeaTalkError as exc:
                    if not SEATALK_REMOVEBG_VENDOR_FALLBACK_ENABLED:
                        raise UploadImageError(f"SeaTalk private image reply failed: {exc}") from exc
                    LOGGER.warning(
                        "SeaTalk direct image reply failed for removebg; falling back to Vendor Tool link | employee_code=%s | error=%s",
                        employee_code,
                        exc,
                    )
                    final_url = upload_image_to_vendor_tool(
                        output_path,
                        owner_email=callback_context.get("email", ""),
                        upload_filename_hint=f"seatalk-{employee_code}-removebg-{int(datetime.now().timestamp())}",
                    )
                    LOGGER.info(
                        "Removebg fallback to Vendor Tool link succeeded | employee_code=%s | final_url=%s",
                        employee_code,
                        final_url,
                    )
                    try:
                        delivery_client.send_image_url(final_url)
                        LOGGER.info(
                            "Removebg vendor image URL reply succeeded | employee_code=%s | final_url=%s",
                            employee_code,
                            final_url,
                        )
                        fallback_reply = (
                            "**Tach nen anh thanh cong**\n"
                            f"*Toi da gui lai anh PNG bang URL anh.*\n"
                            f"- Link ảnh: {final_url}"
                        )
                    except SeaTalkError as nested_exc:
                        LOGGER.warning(
                            "Removebg vendor image URL reply failed; falling back to text link | employee_code=%s | error=%s",
                            employee_code,
                            nested_exc,
                        )
                        fallback_reply = (
                            "**Tach nen anh thanh cong**\n"
                            "*SeaTalk khong nhan anh truc tiep, nen toi tra lai link PNG ket qua.*\n"
                            f"- Link ảnh: {final_url}"
                        )
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
            return fallback_reply

        def _build_report_text(self, report_code: str) -> str:
            try:
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
            except Exception as exc:
                self._notify_superadmins_once(
                    f"report:{report_code}:{type(exc).__name__}:{exc}",
                    "Lỗi dựng báo cáo private/group",
                    f"Report: {report_code}\nError: {type(exc).__name__}: {exc}",
                )
                raise
            return str(package.get("renderedText") or "").strip()

        def _send_thread_report_with_optional_chart(self, client: Any, report_code: str) -> None:
            try:
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
            except Exception as exc:
                self._notify_superadmins_once(
                    f"report:{report_code}:{type(exc).__name__}:{exc}",
                    "Lỗi dựng báo cáo private/group",
                    f"Report: {report_code}\nError: {type(exc).__name__}: {exc}",
                )
                raise
            client.send_text(str(package.get("renderedText") or "").strip())
            for chart_path in [str(item).strip() for item in (package.get("chartPaths") or []) if str(item).strip()]:
                client.send_image_path(chart_path)

        def _send_private_report_with_optional_chart(self, private_client: Any, report_code: str) -> None:
            self._send_thread_report_with_optional_chart(private_client, report_code)

        def _send_private_report_with_interactions(self, private_client: Any, report_code: str) -> None:
            try:
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
            except Exception as exc:
                self._notify_superadmins_once(
                    f"report:{report_code}:{type(exc).__name__}:{exc}",
                    "Lá»—i dá»±ng bÃ¡o cÃ¡o private/group",
                    f"Report: {report_code}\nError: {type(exc).__name__}: {exc}",
                )
                raise
            private_client.send_text(str(package.get("renderedText") or "").strip())
            for chart_path in [str(item).strip() for item in (package.get("chartPaths") or []) if str(item).strip()]:
                private_client.send_image_path(chart_path)
            if package.get("interactiveActions"):
                for interactive_group in build_interactive_groups(package):
                    private_client.send_interactive(build_interactive_group_payload(interactive_group))

        def _send_private_chart_bundle(self, private_client: Any) -> None:
            report_codes = ["SO1", "TOPD_REPORT", "TOPF_REPORT", "TOPH_REPORT"]
            sent_chart_paths: set[str] = set()
            private_client.send_text(
                "**Biểu đồ nhanh 30 ngày**\n"
                "*Tôi đang gửi lần lượt biểu đồ chung KOLs, campaign, official và roblox.*"
            )
            for report_code in report_codes:
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
                for chart_path in [str(item).strip() for item in (package.get("chartPaths") or []) if str(item).strip()]:
                    if chart_path in sent_chart_paths:
                        continue
                    sent_chart_paths.add(chart_path)
                    private_client.send_image_path(chart_path)

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
                seatalk_admin_employee_codes=runtime.get("admin_employee_codes", []),
                seatalk_superadmin_users=runtime["superadmin_users"],
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
        try:
            sync_store_from_github_artifact(runtime)
        except Exception as exc:
            if runtime.get("seatalk_app_id") and runtime.get("seatalk_app_secret") and runtime.get("superadmin_users"):
                send_superadmin_alerts(
                    app_id=runtime["seatalk_app_id"],
                    app_secret=runtime["seatalk_app_secret"],
                    superadmins=runtime["superadmin_users"],
                    title="Lỗi đồng bộ dữ liệu khi khởi động bot",
                    body=f"Phase: sync_on_start\nError: {type(exc).__name__}: {exc}",
                )
            raise
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

