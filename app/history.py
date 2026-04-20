from __future__ import annotations

import json
from datetime import datetime
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
