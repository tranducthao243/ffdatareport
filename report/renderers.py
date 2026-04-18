from __future__ import annotations

from typing import Any


def render_seatalk_package(package: dict[str, Any]) -> str:
    lines = [
        package["title"],
        f"Báo cáo tự động Data Master. Gói dữ liệu: `{package['reportCode']}`.",
        "",
    ]
    for section in package.get("sections", []):
        code = section.get("code")
        if code == "TOPA":
            lines.extend(render_top_by_platform("TOPA: Top video 24h gần nhất", section))
        elif code == "TOPB":
            lines.extend(render_top_by_platform("TOPB: Top video 7 ngày", section))
        elif code == "TOPC":
            lines.extend(render_top_channels("TOPC: Top 5 KOL 7 ngày", section))
        elif code == "TOPE":
            lines.extend(render_tope(section))
        elif code == "TOPD":
            lines.extend(render_topd(section))
        elif code == "TOPF":
            lines.extend(render_topf(section))
        lines.append("")
    return "\n".join(line for line in lines if line is not None).strip()


def render_top_by_platform(title: str, section: dict[str, Any]) -> list[str]:
    lines = [title, f"Khung thời gian: `{section['window']['from']} -> {section['window']['to']}`", "TikTok:"]
    lines.extend(render_ranked_posts(section.get("tiktok", [])))
    lines.append("YouTube:")
    lines.extend(render_ranked_posts(section.get("youtube", [])))
    return lines


def render_top_channels(title: str, section: dict[str, Any]) -> list[str]:
    lines = [title, f"Khung thời gian: `{section['window']['from']} -> {section['window']['to']}`"]
    for index, item in enumerate(section.get("channels", []), start=1):
        lines.append(
            f"{index}. {item['channelName']} | {compact_number(item['totalView'])} view | {item['totalClips']} clip"
        )
    if len(lines) == 2:
        lines.append("- Không có dữ liệu")
    return lines


def render_tope(section: dict[str, Any]) -> list[str]:
    return [
        "TOPE: Tổng quan hệ KOL 7 ngày",
        f"Khung thời gian: `{section['window']['from']} -> {section['window']['to']}`",
        f"- Tổng view: {compact_number(section['totalViews'])}",
        f"- Tổng clip: {section['totalClips']}",
    ]


def render_topd(section: dict[str, Any]) -> list[str]:
    lines = ["TOPD: Báo cáo campaign"]
    campaigns = section.get("campaigns", [])
    if not campaigns:
        return lines + ["- Chưa có campaign được gắn cho group này"]
    for campaign in campaigns:
        lines.extend(
            [
                f"- {campaign['campaignName']} | {', '.join('#' + tag for tag in campaign['hashtags'])}",
                f"  Tổng view: {compact_number(campaign['totalViews'])}",
                f"  Tổng clip: {campaign['totalClips']}",
                f"  KPI: {campaign['kpiPercent']}% / {compact_number(campaign['kpiTarget'])}",
                f"  Còn lại: {campaign['daysLeft']} ngày",
                "  Top TikTok 2 ngày gần nhất:",
            ]
        )
        if campaign.get("topRecentTikTok"):
            for index, item in enumerate(campaign["topRecentTikTok"], start=1):
                lines.append(f"  {index}. {item['channelName']} | {compact_number(item['view'])} | [Link]({item['url']})")
        else:
            lines.append("  - Không có dữ liệu")
    return lines


def render_topf(section: dict[str, Any]) -> list[str]:
    lines = [
        "TOPF: Báo cáo kênh Official",
        f"Top view 3 ngày: `{section['topWindow']['from']} -> {section['topWindow']['to']}`",
    ]
    lines.extend(render_ranked_posts(section.get("topVideos", [])))
    lines.append(f"Tổng hợp 7 ngày: `{section['summaryWindow']['from']} -> {section['summaryWindow']['to']}`")
    for platform, totals in section.get("platformTotals", {}).items():
        lines.append(
            f"- {platform.title()}: {compact_number(totals['totalViews'])} view | {totals['totalClips']} clip"
        )
    return lines


def render_ranked_posts(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- Không có dữ liệu"]
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. {item['channelName']} | {compact_number(item['view'])} | [Link]({item['url']})"
        )
    return lines


def compact_number(value: int) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)
