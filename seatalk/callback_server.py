from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import tempfile
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import zipfile

import requests

from app.pipeline import build_report_package_by_code
from datasocial.exceptions import DatasocialError
from datasocial.presets import load_preset

from .auth import build_seatalk_client
from .callbacks import (
    SeatalkCallbackError,
    extract_click_value,
    extract_sender_employee_code,
    parse_click_payload,
)


LOGGER = logging.getLogger("seatalk.callback_server")


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

                self._write_json(HTTPStatus.OK, {"code": 0})
            except Exception as exc:
                LOGGER.exception("Callback handling failed")
                self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"code": 500, "message": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            LOGGER.info("%s - %s", self.address_string(), format % args)

        def _handle_interactive_click(self, event: dict[str, Any]) -> None:
            employee_code = extract_sender_employee_code(event)
            if not employee_code:
                raise SeatalkCallbackError("Missing employee_code in callback event.")
            raw_value = extract_click_value(event)
            click_payload = parse_click_payload(raw_value)
            action = str(click_payload.get("action") or "").strip()
            if action != "open_report":
                raise SeatalkCallbackError(f"Unsupported interactive action: {action or '-'}")
            target_report_code = str(click_payload.get("target_report_code") or "").strip()
            if not target_report_code:
                raise SeatalkCallbackError("Missing target_report_code in callback payload.")
            if runtime["sync_on_click"]:
                sync_store_from_github_artifact(runtime)

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
            client = build_seatalk_client(
                app_id=runtime["seatalk_app_id"],
                app_secret=runtime["seatalk_app_secret"],
                employee_code=employee_code,
            )
            client.send_text(str(package.get("renderedText") or "").strip())

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
        raise DatasocialError("SEATALK_APP_ID and SEATALK_APP_SECRET are required for callback replies.")
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
