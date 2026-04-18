from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from normalize import build_sqlite_store
from report import build_report_packages, render_seatalk_package
from seatalk import send_report_packages

from .config_loader import load_json, resolve_group_target


def build_store_from_export(
    csv_path: Path,
    db_path: Path,
    *,
    timezone_name: str,
) -> dict[str, Any]:
    return build_sqlite_store(csv_path, db_path, timezone_name=timezone_name)


def build_configured_reports(
    db_path: Path,
    *,
    groups_path: Path,
    reports_path: Path,
    campaigns_path: Path,
    timezone_name: str,
    mode: str,
    now: datetime | None = None,
    send: bool = False,
    seatalk_app_id: str = "",
    seatalk_app_secret: str = "",
) -> dict[str, Any]:
    groups_config = load_json(groups_path)
    reports_config = load_json(reports_path)
    campaigns_config = load_json(campaigns_path)

    packages = build_report_packages(
        db_path,
        groups_config=groups_config,
        reports_config=reports_config,
        campaigns_config=campaigns_config,
        mode=mode,
        timezone_name=timezone_name,
        now=now,
    )
    for package in packages:
        package["resolvedGroupId"] = resolve_group_target(
            next(item for item in groups_config["groups"] if item["name"] == package["groupName"])
        )
        package["renderedText"] = render_seatalk_package(package)

    send_results: list[dict[str, Any]] = []
    if send:
        send_results = send_report_packages(
            packages,
            app_id=seatalk_app_id,
            app_secret=seatalk_app_secret,
        )

    return {
        "generatedAt": (now or datetime.now()).isoformat(),
        "packageCount": len(packages),
        "packages": packages,
        "sendResults": send_results,
    }
