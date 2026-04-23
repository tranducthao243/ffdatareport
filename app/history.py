from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def build_daily_snapshot(payload: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    generated_at = (now or datetime.now()).isoformat()
    snapshot = {
        "generatedAt": generated_at,
        "snapshotDate": generated_at[:10],
        "storeSummary": payload.get("dataHealth", {}).get("storeSummary", {}),
        "sourceScope": payload.get("dataHealth", {}).get("sourceScope", {}),
        "activeCampaigns": payload.get("dataHealth", {}).get("activeCampaigns", []),
        "issues": payload.get("dataHealth", {}).get("issues", []),
        "reports": {},
    }

    for package in payload.get("packages", []):
        report_code = str(package.get("reportCode") or "").strip()
        report_entry: dict[str, Any] = {
            "groupName": package.get("groupName", ""),
            "title": package.get("title", ""),
            "sections": {},
        }
        for section in package.get("sections", []):
            code = str(section.get("code") or "").strip()
            if code == "TOPE":
                report_entry["sections"][code] = {
                    "window": section.get("window", {}),
                    "totalViews": int(section.get("totalViews", 0) or 0),
                    "totalClips": int(section.get("totalClips", 0) or 0),
                }
            elif code == "TOPD":
                report_entry["sections"][code] = {
                    "campaigns": [
                        {
                            "campaignName": item.get("campaignName", ""),
                            "totalViews": int(item.get("totalViews", 0) or 0),
                            "totalClips": int(item.get("totalClips", 0) or 0),
                            "kpiPercent": float(item.get("kpiPercent", 0) or 0),
                            "daysLeft": int(item.get("daysLeft", 0) or 0),
                        }
                        for item in section.get("campaigns", [])
                    ]
                }
            elif code == "TOPF":
                platform_totals = {}
                for platform, totals in (section.get("platformTotals") or {}).items():
                    platform_totals[platform] = {
                        "totalViews": int(totals.get("totalViews", 0) or 0),
                        "totalClips": int(totals.get("totalClips", 0) or 0),
                    }
                report_entry["sections"][code] = {
                    "topWindow": section.get("topWindow", {}),
                    "summaryWindow": section.get("summaryWindow", {}),
                    "platformTotals": platform_totals,
                }
        snapshot["reports"][report_code] = report_entry

    return snapshot


def save_daily_snapshot(snapshot: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def load_daily_snapshots(history_dir: Path | None) -> list[dict[str, Any]]:
    if not history_dir or not history_dir.exists():
        return []
    snapshots: list[dict[str, Any]] = []
    for path in sorted(history_dir.glob("*.json")):
        try:
            snapshots.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    snapshots.sort(key=lambda item: str(item.get("snapshotDate") or ""))
    return snapshots


def _find_snapshot_for_date(snapshots: list[dict[str, Any]], target_date: date) -> dict[str, Any] | None:
    target = target_date.isoformat()
    for snapshot in reversed(snapshots):
        if str(snapshot.get("snapshotDate") or "") == target:
            return snapshot
    return None


def _build_delta(current_value: int, previous_value: int) -> dict[str, int]:
    return {
        "previous": previous_value,
        "current": current_value,
        "change": current_value - previous_value,
    }


def apply_history_deltas(
    payload: dict[str, Any],
    *,
    history_dir: Path | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    snapshots = load_daily_snapshots(history_dir)
    if not snapshots:
        return payload

    today = (now or datetime.now()).date()
    previous_day = _find_snapshot_for_date(snapshots, today - timedelta(days=1))
    previous_week = _find_snapshot_for_date(snapshots, today - timedelta(days=7))

    payload.setdefault("history", {})
    payload["history"]["previousDaySnapshotDate"] = (previous_day or {}).get("snapshotDate", "")
    payload["history"]["previousWeekSnapshotDate"] = (previous_week or {}).get("snapshotDate", "")

    for package in payload.get("packages", []):
        report_code = str(package.get("reportCode") or "").strip()
        current_sections = {str(item.get("code") or "").strip(): item for item in package.get("sections", [])}
        previous_day_sections = ((previous_day or {}).get("reports", {}).get(report_code, {}).get("sections", {}))
        previous_week_sections = ((previous_week or {}).get("reports", {}).get(report_code, {}).get("sections", {}))

        if "TOPE" in current_sections:
            current = current_sections["TOPE"]
            deltas: dict[str, Any] = {}
            if "TOPE" in previous_day_sections:
                previous = previous_day_sections["TOPE"]
                deltas["vsPreviousDay"] = {
                    "views": _build_delta(int(current.get("totalViews", 0) or 0), int(previous.get("totalViews", 0) or 0)),
                    "clips": _build_delta(int(current.get("totalClips", 0) or 0), int(previous.get("totalClips", 0) or 0)),
                }
            if "TOPE" in previous_week_sections:
                previous = previous_week_sections["TOPE"]
                deltas["vsPreviousWeek"] = {
                    "views": _build_delta(int(current.get("totalViews", 0) or 0), int(previous.get("totalViews", 0) or 0)),
                    "clips": _build_delta(int(current.get("totalClips", 0) or 0), int(previous.get("totalClips", 0) or 0)),
                }
            if deltas:
                current["historyCompare"] = deltas
                current["historyLabels"] = {
                    "previousDaySnapshotDate": (previous_day or {}).get("snapshotDate", ""),
                    "previousWeekSnapshotDate": (previous_week or {}).get("snapshotDate", ""),
                }

        if "TOPF" in current_sections:
            current = current_sections["TOPF"]
            current_total_views = sum(int(item.get("totalViews", 0) or 0) for item in (current.get("platformTotals") or {}).values())
            current_total_clips = sum(int(item.get("totalClips", 0) or 0) for item in (current.get("platformTotals") or {}).values())
            deltas = {}
            if "TOPF" in previous_day_sections:
                previous = previous_day_sections["TOPF"]
                previous_views = sum(int(item.get("totalViews", 0) or 0) for item in (previous.get("platformTotals") or {}).values())
                previous_clips = sum(int(item.get("totalClips", 0) or 0) for item in (previous.get("platformTotals") or {}).values())
                deltas["vsPreviousDay"] = {
                    "views": _build_delta(current_total_views, previous_views),
                    "clips": _build_delta(current_total_clips, previous_clips),
                }
            if "TOPF" in previous_week_sections:
                previous = previous_week_sections["TOPF"]
                previous_views = sum(int(item.get("totalViews", 0) or 0) for item in (previous.get("platformTotals") or {}).values())
                previous_clips = sum(int(item.get("totalClips", 0) or 0) for item in (previous.get("platformTotals") or {}).values())
                deltas["vsPreviousWeek"] = {
                    "views": _build_delta(current_total_views, previous_views),
                    "clips": _build_delta(current_total_clips, previous_clips),
                }
            if deltas:
                current["historyCompare"] = deltas
                current["historyLabels"] = {
                    "previousDaySnapshotDate": (previous_day or {}).get("snapshotDate", ""),
                    "previousWeekSnapshotDate": (previous_week or {}).get("snapshotDate", ""),
                }

        if "TOPD" in current_sections:
            current = current_sections["TOPD"]
            previous_day_campaigns = {item.get("campaignName"): item for item in previous_day_sections.get("TOPD", {}).get("campaigns", [])}
            previous_week_campaigns = {item.get("campaignName"): item for item in previous_week_sections.get("TOPD", {}).get("campaigns", [])}
            for campaign in current.get("campaigns", []):
                campaign_deltas: dict[str, Any] = {}
                campaign_name = campaign.get("campaignName")
                if campaign_name in previous_day_campaigns:
                    previous = previous_day_campaigns[campaign_name]
                    campaign_deltas["vsPreviousDay"] = {
                        "views": _build_delta(int(campaign.get("totalViews", 0) or 0), int(previous.get("totalViews", 0) or 0)),
                        "clips": _build_delta(int(campaign.get("totalClips", 0) or 0), int(previous.get("totalClips", 0) or 0)),
                    }
                if campaign_name in previous_week_campaigns:
                    previous = previous_week_campaigns[campaign_name]
                    campaign_deltas["vsPreviousWeek"] = {
                        "views": _build_delta(int(campaign.get("totalViews", 0) or 0), int(previous.get("totalViews", 0) or 0)),
                        "clips": _build_delta(int(campaign.get("totalClips", 0) or 0), int(previous.get("totalClips", 0) or 0)),
                    }
                if campaign_deltas:
                    campaign["historyCompare"] = campaign_deltas
                    campaign["historyLabels"] = {
                        "previousDaySnapshotDate": (previous_day or {}).get("snapshotDate", ""),
                        "previousWeekSnapshotDate": (previous_week or {}).get("snapshotDate", ""),
                    }

    return payload
