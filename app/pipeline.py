from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from datasocial.exceptions import DatasocialError
from normalize import build_sqlite_store
from report import build_report_packages, render_seatalk_package
from seatalk import send_report_packages

from .config_loader import (
    format_validation_errors,
    load_json,
    resolve_group_target,
    validate_reporting_config,
)


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
    validation = validate_reporting_config(groups_config, reports_config, campaigns_config)
    if validation["errors"]:
        raise DatasocialError(format_validation_errors(validation))

    packages = build_report_packages(
        db_path,
        groups_config=groups_config,
        reports_config=reports_config,
        campaigns_config=campaigns_config,
        invalid_group_names=set(validation["invalidGroupNames"]),
        mode=mode,
        timezone_name=timezone_name,
        now=now,
    )
    group_lookup = {item["name"]: item for item in groups_config["groups"]}
    for package in packages:
        group = group_lookup[package["groupName"]]
        package["resolvedGroupId"] = resolve_group_target(group)
        package["renderedText"] = render_seatalk_package(package)
        package["sectionCodes"] = [section["code"] for section in package["sections"]]
        package["sectionCount"] = len(package["sections"])

    send_results: list[dict[str, Any]] = []
    if send:
        send_results = send_report_packages(
            packages,
            app_id=seatalk_app_id,
            app_secret=seatalk_app_secret,
        )

    package_summaries = [
        {
            "groupName": package["groupName"],
            "reportCode": package["reportCode"],
            "sectionCodes": package["sectionCodes"],
            "sectionCount": package["sectionCount"],
            "hasResolvedGroupId": bool(package["resolvedGroupId"]),
        }
        for package in packages
    ]
    sent_count = sum(1 for item in send_results if item["status"] == "sent")
    skipped_count = sum(1 for item in send_results if item["status"] == "skipped")
    failed_count = sum(1 for item in send_results if item["status"] == "failed")

    return {
        "generatedAt": (now or datetime.now()).isoformat(),
        "packageCount": len(packages),
        "packageSummaries": package_summaries,
        "validation": {
            "errorCount": len(validation["errors"]),
            "warningCount": len(validation["warnings"]),
            "warnings": validation["warnings"],
            "groupStates": validation["groupStates"],
        },
        "summary": {
            "packagesBuilt": len(packages),
            "warnings": len(validation["warnings"]),
            "sent": sent_count,
            "skipped": skipped_count,
            "failed": failed_count,
        },
        "packages": packages,
        "sendResults": send_results,
    }
