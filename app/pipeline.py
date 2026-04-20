from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from datasocial.exceptions import DatasocialError
from normalize import build_sqlite_store
from report import build_report_packages, render_seatalk_package
from seatalk import build_interactive_actions, build_seatalk_client, send_report_packages

from .config_loader import (
    format_validation_errors,
    load_json,
    resolve_group_target,
    validate_reporting_config,
)
from .history import apply_history_deltas, build_daily_snapshot, save_daily_snapshot
from .health import build_health_snapshot, format_health_alert


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
    source_scope: dict[str, list[int]] | None = None,
    now: datetime | None = None,
    send: bool = False,
    seatalk_app_id: str = "",
    seatalk_app_secret: str = "",
    seatalk_admin_employee_codes: list[str] | None = None,
    history_path: Path | None = None,
    history_dir: Path | None = None,
) -> dict[str, Any]:
    groups_config = load_json(groups_path)
    reports_config = load_json(reports_path)
    campaigns_config = load_json(campaigns_path)
    validation = validate_reporting_config(
        groups_config,
        reports_config,
        campaigns_config,
        source_scope=source_scope,
    )
    if validation["errors"]:
        raise DatasocialError(format_validation_errors(validation))

    packages = build_report_packages(
        db_path,
        groups_config=groups_config,
        reports_config=reports_config,
        campaigns_config=campaigns_config,
        invalid_group_names=set(validation["invalidGroupNames"]),
        blocked_group_names=set(validation["blockedGroupNames"]),
        mode=mode,
        timezone_name=timezone_name,
        now=now,
    )
    group_lookup = {item["name"]: item for item in groups_config["groups"]}
    for package in packages:
        group = group_lookup[package["groupName"]]
        package["resolvedGroupId"] = resolve_group_target(group)
        package["interactiveActions"] = build_interactive_actions(package)
        package["renderedText"] = render_seatalk_package(package)
        package["sectionCodes"] = [section["code"] for section in package["sections"]]
        package["sectionCount"] = len(package["sections"])

    health_snapshot = build_health_snapshot(
        {
            "packages": packages,
            "validation": {
                "warnings": validation["warnings"],
            },
        },
        db_path=db_path,
        source_scope=source_scope,
        campaigns_config=campaigns_config,
        now=now,
    )

    send_results: list[dict[str, Any]] = []
    if send:
        if health_snapshot["blockSend"]:
            send_results = [
                {
                    "groupName": package["groupName"],
                    "reportCode": package["reportCode"],
                    "status": "skipped",
                    "groupId": package["resolvedGroupId"],
                    "reason": "data_health_blocked",
                    "message": "Group send blocked because data health issues were detected.",
                }
                for package in packages
            ]
            admin_codes = seatalk_admin_employee_codes or []
            for employee_code in admin_codes:
                try:
                    build_seatalk_client(
                        app_id=seatalk_app_id,
                        app_secret=seatalk_app_secret,
                        employee_code=employee_code,
                    ).send_text(format_health_alert(health_snapshot))
                    send_results.append(
                        {
                            "groupName": "__admin__",
                            "reportCode": "HEALTH_ALERT",
                            "status": "sent",
                            "employeeCode": employee_code,
                        }
                    )
                except Exception as exc:
                    send_results.append(
                        {
                            "groupName": "__admin__",
                            "reportCode": "HEALTH_ALERT",
                            "status": "failed",
                            "employeeCode": employee_code,
                            "reason": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
        else:
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
            "interactiveActionCount": len(package.get("interactiveActions", [])),
        }
        for package in packages
    ]
    sent_count = sum(1 for item in send_results if item["status"] == "sent")
    skipped_count = sum(1 for item in send_results if item["status"] == "skipped")
    failed_count = sum(1 for item in send_results if item["status"] == "failed")
    blocked_count = sum(1 for item in validation["groupStates"] if item["status"] == "blocked")

    payload = {
        "generatedAt": (now or datetime.now()).isoformat(),
        "packageCount": len(packages),
        "packageSummaries": package_summaries,
        "validation": {
            "errorCount": len(validation["errors"]),
            "warningCount": len(validation["warnings"]),
            "warnings": validation["warnings"],
            "groupStates": validation["groupStates"],
        },
        "dataHealth": health_snapshot,
        "summary": {
            "packagesBuilt": len(packages),
            "warnings": len(validation["warnings"]),
            "blocked": blocked_count,
            "sent": sent_count,
            "skipped": skipped_count,
            "failed": failed_count,
        },
        "packages": packages,
        "sendResults": send_results,
    }
    payload = apply_history_deltas(payload, history_dir=history_dir, now=now)
    if history_path:
        save_daily_snapshot(build_daily_snapshot(payload, now=now), history_path)
    return payload


def build_report_package_by_code(
    db_path: Path,
    *,
    report_code: str,
    groups_path: Path,
    reports_path: Path,
    campaigns_path: Path,
    timezone_name: str,
    mode: str,
    source_scope: dict[str, list[int]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    groups_config = load_json(groups_path)
    reports_config = load_json(reports_path)
    campaigns_config = load_json(campaigns_path)
    validation = validate_reporting_config(
        groups_config,
        reports_config,
        campaigns_config,
        source_scope=source_scope,
    )
    if validation["errors"]:
        raise DatasocialError(format_validation_errors(validation))

    invalid_group_names = set(validation["invalidGroupNames"])
    blocked_group_names = set(validation["blockedGroupNames"])
    selected_group = None
    for group in groups_config.get("groups", []):
        if not group.get("enabled", True):
            continue
        if group["name"] in invalid_group_names or group["name"] in blocked_group_names:
            continue
        if str(group.get("report_code") or "").strip() == report_code:
            selected_group = group
            break
    if selected_group is None:
        raise DatasocialError(f"No enabled group is configured for report_code '{report_code}'.")

    packages = build_report_packages(
        db_path,
        groups_config={"groups": [selected_group]},
        reports_config=reports_config,
        campaigns_config=campaigns_config,
        invalid_group_names=set(),
        blocked_group_names=set(),
        mode=mode,
        timezone_name=timezone_name,
        now=now,
    )
    if not packages:
        raise DatasocialError(f"Unable to build package for report_code '{report_code}'.")

    package = packages[0]
    package["resolvedGroupId"] = resolve_group_target(selected_group)
    package["interactiveActions"] = build_interactive_actions(package)
    package["renderedText"] = render_seatalk_package(package)
    package["sectionCodes"] = [section["code"] for section in package["sections"]]
    package["sectionCount"] = len(package["sections"])
    return package
