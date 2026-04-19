from __future__ import annotations

import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

from normalize import sqlite_store_summary


CATEGORY_LABELS = {
    13: "Official",
    14: "Gameplay Creator",
    22: "Entertainment Creator",
    23: "Esports Creator",
    24: "Community Creator",
}

PLATFORM_LABELS = {
    0: "TikTok",
    1: "Facebook",
    2: "YouTube",
}


def compact_number(value: int) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def normalize_command_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(ascii_text.strip().lower().split())


def classify_private_command(text: str) -> str:
    normalized = normalize_command_text(text)
    if not normalized:
        return "help"
    if normalized in {"help", "/help", "menu", "/menu", "lenh", "commands"}:
        return "help"
    if normalized in {"health", "status", "summary", "health check"}:
        return "health"
    if normalized in {"data", "du lieu", "database", "db"}:
        return "data"
    if normalized in {"scope", "source", "nguon", "nguon du lieu"}:
        return "scope"
    if normalized in {"campaign", "topd", "chien dich"}:
        return "campaign"
    if normalized in {"official", "topf", "kenh official"}:
        return "official"
    if normalized in {"refresh", "sync", "lam moi", "dong bo"}:
        return "refresh"
    return "unknown"


def list_active_campaigns(campaigns_config: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    today = (now or datetime.now()).date()
    active: list[dict[str, Any]] = []
    for campaign in campaigns_config:
        start_text = str(campaign.get("start_date") or "").strip()
        end_text = str(campaign.get("end_date") or "").strip()
        if not start_text or not end_text:
            continue
        start_date = date.fromisoformat(start_text)
        end_date = date.fromisoformat(end_text)
        if start_date <= today <= end_date:
            active.append(campaign)
    return active


def format_source_scope(source_scope: dict[str, list[int]] | None) -> dict[str, Any]:
    category_ids = list(source_scope.get("category_ids", [])) if source_scope else []
    platform_ids = list(source_scope.get("platform_ids", [])) if source_scope else []
    return {
        "categoryIds": category_ids,
        "platformIds": platform_ids,
        "categoryLabels": [CATEGORY_LABELS.get(item, str(item)) for item in category_ids],
        "platformLabels": [PLATFORM_LABELS.get(item, str(item)) for item in platform_ids],
    }


def build_health_snapshot(
    payload: dict[str, Any],
    *,
    db_path: Path,
    source_scope: dict[str, list[int]] | None,
    campaigns_config: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    store = sqlite_store_summary(db_path)
    scope = format_source_scope(source_scope)
    active_campaigns = list_active_campaigns(campaigns_config, now=now)
    issues: list[dict[str, str]] = []

    if store["postCount"] <= 0:
        issues.append(
            {
                "severity": "critical",
                "code": "store_empty",
                "message": "Kho du lieu SQLite dang rong, khong co bai viet nao de gui bao cao.",
            }
        )

    for warning in payload.get("validation", {}).get("warnings", []):
        if warning.get("code") == "official_source_disabled":
            issues.append(
                {
                    "severity": "critical",
                    "code": "official_scope_missing",
                    "message": warning.get("message", "Official source scope dang thieu."),
                }
            )

    for package in payload.get("packages", []):
        for section in package.get("sections", []):
            code = str(section.get("code") or "").strip()
            if code == "TOPF":
                official_total_clips = sum(
                    int(item.get("totalClips", 0))
                    for item in (section.get("platformTotals") or {}).values()
                )
                if official_total_clips <= 0:
                    issues.append(
                        {
                            "severity": "critical",
                            "code": "official_missing_data",
                            "message": "Kenh Official khong co clip nao trong cua so tong hop 7 ngay.",
                        }
                    )
            elif code == "TOPD":
                for campaign in section.get("campaigns", []):
                    if int(campaign.get("daysLeft", 0)) >= 0 and int(campaign.get("totalClips", 0)) <= 0:
                        issues.append(
                            {
                                "severity": "critical",
                                "code": "campaign_missing_data",
                                "message": (
                                    f"Campaign {campaign.get('campaignName', '-')} dang khong co clip nao "
                                    "trong cua so theo doi hien tai."
                                ),
                            }
                        )
                    elif float(campaign.get("kpiPercent", 0)) < 50 and int(campaign.get("daysLeft", 0)) <= 7:
                        issues.append(
                            {
                                "severity": "warning",
                                "code": "campaign_kpi_low",
                                "message": (
                                    f"Campaign {campaign.get('campaignName', '-')} moi dat "
                                    f"{campaign.get('kpiPercent', 0)}% KPI va chi con {campaign.get('daysLeft', 0)} ngay."
                                ),
                            }
                        )
            elif code == "TOPE":
                daily = list(section.get("daily") or [])
                if len(daily) >= 2:
                    previous = int(daily[-2].get("totalClips", 0))
                    latest = int(daily[-1].get("totalClips", 0))
                    if previous >= 10 and latest <= max(1, int(previous * 0.5)):
                        issues.append(
                            {
                                "severity": "warning",
                                "code": "clip_drop_anomaly",
                                "message": (
                                    f"So clip he KOL ngay gan nhat giam manh: {latest} clip so voi {previous} clip truoc do."
                                ),
                            }
                        )

    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for issue in issues:
        key = (issue["severity"], issue["code"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)

    return {
        "generatedAt": (now or datetime.now()).isoformat(),
        "storeSummary": store,
        "sourceScope": scope,
        "activeCampaigns": [
            {
                "name": item.get("name", ""),
                "startDate": item.get("start_date", ""),
                "endDate": item.get("end_date", ""),
                "kpiTarget": int(item.get("kpi_view_target", 0) or 0),
            }
            for item in active_campaigns
        ],
        "issues": deduped,
        "blockSend": any(item["severity"] == "critical" for item in deduped),
    }


def format_health_report(snapshot: dict[str, Any]) -> str:
    store = snapshot["storeSummary"]
    lines = [
        "**Tinh trang du lieu**",
        f"*Kho du lieu: `{store['dbPath']}`*",
        f"- Bai viet: {store['postCount']}",
        f"- Kenh: {store['channelCount']}",
        f"- Tong view: {compact_number(store['totalView'])}",
    ]
    active_campaigns = snapshot.get("activeCampaigns") or []
    if active_campaigns:
        names = ", ".join(item["name"] for item in active_campaigns)
        lines.append(f"- Campaign dang active: {names}")
    else:
        lines.append("- Campaign dang active: khong co")
    lines.append("")
    lines.append("**Canh bao hien tai**")
    issues = snapshot.get("issues") or []
    if not issues:
        lines.append("- Khong co canh bao nghiem trong.")
    else:
        for issue in issues:
            prefix = "Nghiem trong" if issue["severity"] == "critical" else "Luu y"
            lines.append(f"- {prefix}: {issue['message']}")
    return "\n".join(lines)


def format_data_report(snapshot: dict[str, Any]) -> str:
    store = snapshot["storeSummary"]
    platform_counts = store.get("platformCounts", {})
    lines = [
        "**Du lieu dang dung**",
        f"*SQLite: `{store['dbPath']}`*",
        f"- Bai viet: {store['postCount']}",
        f"- Kenh: {store['channelCount']}",
        f"- Tong view: {compact_number(store['totalView'])}",
    ]
    if platform_counts:
        lines.append("- Phan bo theo nen tang:")
        for platform, count in platform_counts.items():
            lines.append(f"  - {platform}: {count} bai")
    return "\n".join(lines)


def format_scope_report(snapshot: dict[str, Any]) -> str:
    scope = snapshot["sourceScope"]
    category_labels = ", ".join(scope["categoryLabels"]) or "-"
    platform_labels = ", ".join(scope["platformLabels"]) or "-"
    return "\n".join(
        [
            "**Source scope hien tai**",
            f"- Category IDs: {', '.join(str(item) for item in scope['categoryIds']) or '-'}",
            f"- Category labels: {category_labels}",
            f"- Platform IDs: {', '.join(str(item) for item in scope['platformIds']) or '-'}",
            f"- Platform labels: {platform_labels}",
        ]
    )


def format_campaign_status_report(snapshot: dict[str, Any]) -> str:
    active_campaigns = snapshot.get("activeCampaigns") or []
    lines = ["**Campaign dang active**"]
    if not active_campaigns:
        lines.append("- Khong co campaign nao trong giai doan active.")
        return "\n".join(lines)
    for item in active_campaigns:
        lines.append(
            f"- {item['name']} | `{item['startDate']} -> {item['endDate']}` | KPI {compact_number(item['kpiTarget'])}"
        )
    return "\n".join(lines)


def format_health_alert(snapshot: dict[str, Any]) -> str:
    lines = [
        "**Canh bao gui group da bi chan**",
        "*Bot tam dung gui bao cao vao group vi du lieu hien tai dang co van de.*",
        "",
    ]
    for issue in snapshot.get("issues") or []:
        lines.append(f"- {issue['message']}")
    return "\n".join(lines).strip()
