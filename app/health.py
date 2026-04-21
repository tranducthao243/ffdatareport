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
    119: "Trend nhảy",
    368: "Roblox Content",
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


def format_issue_label(code: str) -> str:
    labels = {
        "store_empty": "Kho dữ liệu đang rỗng",
        "official_scope_missing": "Official scope bị thiếu",
        "official_missing_data": "Official mất data",
        "campaign_missing_data": "Campaign mất data",
        "campaign_kpi_low": "Campaign đang tụt KPI",
        "clip_drop_anomaly": "Số clip giảm bất thường",
    }
    return labels.get(code, code.replace("_", " ").strip().title())


def normalize_command_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(ascii_text.strip().lower().split())


def classify_private_command(text: str) -> str:
    normalized = normalize_command_text(text)
    if not normalized:
        return "help"
    if normalized in {".", "help", "/help", "menu", "/menu", "lenh", "commands"}:
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
    if normalized in {"dance", "trend nhay", "topg"}:
        return "dance"
    if normalized in {"roblox", "roblox content", "toph"}:
        return "roblox"
    if normalized in {"webcompany", "web", "link", "links"}:
        return "web"
    if normalized in {"shortlink", "link ngan", "tao shortlink", "rut gon link"}:
        return "shortlink"
    if normalized in {"uploadimage", "upload anh", "gui anh len web", "up anh"}:
        return "uploadimage"
    if normalized in {"enhanceimage", "lam net anh", "lam net", "upscale"}:
        return "enhanceimage"
    if normalized in {"removebg", "tach nen", "xoa nen", "remove background"}:
        return "removebg"
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
                "message": "Kho dữ liệu SQLite đang rỗng, không có bài viết nào để gửi báo cáo.",
            }
        )

    for warning in payload.get("validation", {}).get("warnings", []):
        if warning.get("code") == "official_source_disabled":
            issues.append(
                {
                    "severity": "critical",
                    "code": "official_scope_missing",
                    "message": warning.get("message", "Official source scope đang thiếu."),
                }
            )

    comparisons: dict[str, Any] = {}

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
                            "message": "Kênh Official không có clip nào trong cửa sổ tổng hợp 7 ngày.",
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
                                    f"Campaign {campaign.get('campaignName', '-')} đang không có clip nào "
                                    "trong cửa sổ theo dõi hiện tại."
                                ),
                            }
                        )
                    elif float(campaign.get("kpiPercent", 0)) < 50 and int(campaign.get("daysLeft", 0)) <= 7:
                        issues.append(
                            {
                                "severity": "warning",
                                "code": "campaign_kpi_low",
                                "message": (
                                    f"Campaign {campaign.get('campaignName', '-')} mới đạt "
                                    f"{campaign.get('kpiPercent', 0)}% KPI và chỉ còn {campaign.get('daysLeft', 0)} ngày."
                                ),
                            }
                        )
            elif code == "TOPE":
                if section.get("historyCompare"):
                    comparisons["kolOverview"] = section["historyCompare"]
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
                                    f"Số clip hệ KOL ngày gần nhất giảm mạnh: {latest} clip so với {previous} clip trước đó."
                                ),
                            }
                        )

    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, str]] = []
    for issue in issues:
        key = (issue["severity"], issue["code"], issue["message"])
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
        "comparisons": comparisons,
        "blockSend": any(item["severity"] == "critical" for item in deduped),
    }


def format_health_report(snapshot: dict[str, Any]) -> str:
    store = snapshot["storeSummary"]
    lines = [
        "**Tình trạng dữ liệu**",
        f"*Kho dữ liệu: `{store['dbPath']}`*",
        f"- Bài viết: {store['postCount']}",
        f"- Kênh: {store['channelCount']}",
        f"- Tổng view: {compact_number(store['totalView'])}",
    ]
    active_campaigns = snapshot.get("activeCampaigns") or []
    if active_campaigns:
        names = ", ".join(item["name"] for item in active_campaigns)
        lines.append(f"- Campaign đang active: {names}")
    else:
        lines.append("- Campaign đang active: không có")
    kol_compare = (snapshot.get("comparisons") or {}).get("kolOverview") or {}
    if kol_compare.get("vsPreviousDay"):
        lines.append(
            "- Tổng view hệ KOL so với hôm qua: "
            f"{format_change(int(kol_compare['vsPreviousDay']['views']['change']))}"
        )
    if kol_compare.get("vsPreviousWeek"):
        lines.append(
            "- Tổng view hệ KOL so với tuần trước: "
            f"{format_change(int(kol_compare['vsPreviousWeek']['views']['change']))}"
        )
    lines.append("")
    lines.append("**Cảnh báo hiện tại**")
    issues = snapshot.get("issues") or []
    if not issues:
        lines.append("- Không có cảnh báo nghiêm trọng.")
    else:
        for issue in issues:
            prefix = "Nghiêm trọng" if issue["severity"] == "critical" else "Lưu ý"
            lines.append(f"- {prefix}: {issue['message']}")
    return "\n".join(lines)


def format_data_report(snapshot: dict[str, Any]) -> str:
    store = snapshot["storeSummary"]
    platform_counts = store.get("platformCounts", {})
    lines = [
        "**Dữ liệu đang dùng**",
        f"*SQLite: `{store['dbPath']}`*",
        f"- Khung dữ liệu đang quét: `{store.get('minPublishedDate', '-')} -> {store.get('maxPublishedDate', '-')}`",
        f"- Cập nhật lần cuối: `{store.get('lastInsertedAt', '-')}`",
        f"- Bài viết: {store['postCount']}",
        f"- Kênh: {store['channelCount']}",
        f"- Tổng view: {compact_number(store['totalView'])}",
    ]
    active_campaigns = snapshot.get("activeCampaigns") or []
    if active_campaigns:
        lines.append("- Campaign đang active: " + ", ".join(item["name"] for item in active_campaigns))
    else:
        lines.append("- Campaign đang active: không có")
    if platform_counts:
        lines.append("- Phân bố theo nền tảng:")
        for platform, count in platform_counts.items():
            lines.append(f"  - {platform}: {count} bài")
    return "\n".join(lines)


def format_scope_report(snapshot: dict[str, Any]) -> str:
    scope = snapshot["sourceScope"]
    category_labels = ", ".join(scope["categoryLabels"]) or "-"
    platform_labels = ", ".join(scope["platformLabels"]) or "-"
    return "\n".join(
        [
            "**Source scope hiện tại**",
            f"- Category IDs: {', '.join(str(item) for item in scope['categoryIds']) or '-'}",
            f"- Category labels: {category_labels}",
            f"- Platform IDs: {', '.join(str(item) for item in scope['platformIds']) or '-'}",
            f"- Platform labels: {platform_labels}",
        ]
    )


def format_campaign_status_report(snapshot: dict[str, Any]) -> str:
    active_campaigns = snapshot.get("activeCampaigns") or []
    lines = ["**Campaign đang active**"]
    if not active_campaigns:
        lines.append("- Không có campaign nào trong giai đoạn active.")
        return "\n".join(lines)
    for item in active_campaigns:
        lines.append(
            f"- {item['name']} | `{item['startDate']} -> {item['endDate']}` | KPI {compact_number(item['kpiTarget'])}"
        )
    return "\n".join(lines)


def format_health_alert(snapshot: dict[str, Any]) -> str:
    store = snapshot.get("storeSummary", {})
    critical_issues = [item for item in (snapshot.get("issues") or []) if item.get("severity") == "critical"]
    warning_issues = [item for item in (snapshot.get("issues") or []) if item.get("severity") == "warning"]
    active_campaigns = snapshot.get("activeCampaigns") or []
    lines = [
        "**Cảnh báo dữ liệu FFVN**",
        "*Bot tạm dừng gửi báo cáo vào group vì phát hiện vấn đề trong bộ dữ liệu hiện tại.*",
        "",
        f"- Cập nhật lần cuối: `{store.get('lastInsertedAt') or snapshot.get('generatedAt', '-')}`",
        f"- Dữ liệu đang bao phủ: `{store.get('minPublishedDate') or '-'} -> {store.get('maxPublishedDate') or '-'}`",
        f"- Tổng bài viết: {store.get('postCount', 0)} | Tổng kênh: {store.get('channelCount', 0)}",
    ]
    if active_campaigns:
        lines.append("- Campaign đang active: " + ", ".join(item.get("name", "-") for item in active_campaigns))
    lines.extend(
        [
            "",
            "**Nghiêm trọng**",
        ]
    )
    if critical_issues:
        for issue in critical_issues:
            lines.append(f"- {format_issue_label(issue['code'])}: {issue['message']}")
    else:
        lines.append("- Không có lỗi nghiêm trọng.")
    lines.extend(
        [
            "",
            "**Cảnh báo / Theo dõi thêm**",
        ]
    )
    if warning_issues:
        for issue in warning_issues:
            lines.append(f"- {format_issue_label(issue['code'])}: {issue['message']}")
    else:
        lines.append("- Không có cảnh báo cần theo dõi thêm.")
    lines.extend(
        [
            "",
            "*Nếu cần mở quyền bot hoặc kiểm tra lại nguồn dữ liệu, vui lòng liên hệ ducthao.tran@garena.vn.*",
        ]
    )
    return "\n".join(lines).strip()


def format_change(change: int) -> str:
    if change > 0:
        return f"Tăng {compact_number(change)}"
    if change < 0:
        return f"Giảm {compact_number(abs(change))}"
    return "Không đổi"
