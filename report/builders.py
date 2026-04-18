from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from analyze import analyze_topa, analyze_topb, analyze_topc, analyze_topd, analyze_tope, analyze_topf


def build_report_packages(
    db_path: Path,
    *,
    groups_config: dict[str, Any],
    reports_config: dict[str, Any],
    campaigns_config: list[dict[str, Any]],
    mode: str,
    timezone_name: str,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    campaign_by_name = {item["name"]: item for item in campaigns_config}
    packages: list[dict[str, Any]] = []
    for group in groups_config.get("groups", []):
        if not group.get("enabled", True):
            continue
        report_code = group["report_code"]
        report_def = reports_config["reports"][report_code]
        package = {
            "groupName": group["name"],
            "groupId": group.get("group_id", ""),
            "groupIdEnv": group.get("group_id_env", ""),
            "reportCode": report_code,
            "title": group.get("title") or report_def.get("title") or report_code,
            "generatedAt": (now or datetime.now()).isoformat(),
            "sections": [],
        }
        for analyzer_code in report_def.get("sections", []):
            package["sections"].append(
                run_analyzer(
                    analyzer_code,
                    db_path=db_path,
                    campaigns=campaign_by_name,
                    group=group,
                    mode=mode,
                    timezone_name=timezone_name,
                    now=now,
                )
            )
        packages.append(package)
    return packages


def run_analyzer(
    analyzer_code: str,
    *,
    db_path: Path,
    campaigns: dict[str, dict[str, Any]],
    group: dict[str, Any],
    mode: str,
    timezone_name: str,
    now: datetime | None,
) -> dict[str, Any]:
    if analyzer_code == "TOPA":
        return analyze_topa(db_path, mode=mode, timezone_name=timezone_name, now=now)
    if analyzer_code == "TOPB":
        return analyze_topb(db_path, mode=mode, timezone_name=timezone_name, now=now)
    if analyzer_code == "TOPC":
        return analyze_topc(db_path, mode=mode, timezone_name=timezone_name, now=now)
    if analyzer_code == "TOPE":
        return analyze_tope(db_path, mode=mode, timezone_name=timezone_name, now=now)
    if analyzer_code == "TOPF":
        return analyze_topf(db_path, mode=mode, timezone_name=timezone_name, now=now)
    if analyzer_code == "TOPD":
        campaign_names = group.get("campaign_names") or []
        return {
            "code": "TOPD",
            "title": "TOPD",
            "campaigns": [
                analyze_topd(
                    db_path,
                    campaign=campaigns[name],
                    mode=mode,
                    timezone_name=timezone_name,
                    now=now,
                )
                for name in campaign_names
                if name in campaigns
            ],
        }
    raise ValueError(f"Unsupported analyzer code: {analyzer_code}")
