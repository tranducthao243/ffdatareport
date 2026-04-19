from __future__ import annotations

from typing import Any


def render_seatalk_package(package: dict[str, Any]) -> str:
    lines = [
        f"**{str(package['title']).strip()}**",
        f"*Ban tom tat du lieu tu dong tu Data Master | Goi du lieu: `{package['reportCode']}`*",
        "",
    ]
    for section in package.get("sections", []):
        code = str(section.get("code") or "").strip()
        if code == "TOPA":
            lines.extend(render_top_by_platform("Video noi bat trong 24 gio qua", section))
        elif code == "TOPB":
            lines.extend(render_top_by_platform("Video noi bat trong 7 ngay qua", section))
        elif code == "TOPC":
            lines.extend(render_top_channels("5 kenh KOL noi bat trong 7 ngay qua", section))
        elif code == "TOPE":
            lines.extend(render_tope(section))
        elif code == "TOPD":
            lines.extend(render_topd(section))
        elif code == "TOPF":
            lines.extend(render_topf(section))
        lines.append("")
    return "\n".join(line for line in lines if line is not None).strip()


def render_top_by_platform(title: str, section: dict[str, Any]) -> list[str]:
    lines = [
        f"**{title}**",
        f"*Khung thoi gian: `{section['window']['from']} -> {section['window']['to']}`*",
        "",
        "*TikTok*",
    ]
    lines.extend(render_ranked_posts(section.get("tiktok", [])))
    lines.append("")
    lines.append("*YouTube*")
    lines.extend(render_ranked_posts(section.get("youtube", [])))
    return lines


def render_top_channels(title: str, section: dict[str, Any]) -> list[str]:
    lines = [f"**{title}**", f"*Khung thoi gian: `{section['window']['from']} -> {section['window']['to']}`*"]
    for index, item in enumerate(section.get("channels", []), start=1):
        lines.append(
            f"{index}. {item['channelName']} | {compact_number(item['totalView'])} view | {item['totalClips']} clip"
        )
    if len(lines) == 2:
        lines.append("- Chua co du lieu.")
    return lines


def render_tope(section: dict[str, Any]) -> list[str]:
    return [
        "**Tong quan hieu qua he KOL trong 7 ngay qua**",
        f"*Khung thoi gian: `{section['window']['from']} -> {section['window']['to']}`*",
        f"- Tong view: {compact_number(section['totalViews'])}",
        f"- Tong clip: {section['totalClips']}",
    ]


def render_topd(section: dict[str, Any]) -> list[str]:
    lines = ["**Tien do campaign**"]
    campaigns = section.get("campaigns", [])
    if not campaigns:
        return lines + ["- Chua co campaign nao duoc gan cho nhom nay."]
    for campaign in campaigns:
        lines.extend(
            [
                f"- **{campaign['campaignName']}** | {', '.join('#' + tag for tag in campaign['hashtags'])}",
                f"  Tong view: {compact_number(campaign['totalViews'])}",
                f"  Tong clip: {campaign['totalClips']}",
                f"  Muc tieu KPI: {campaign['kpiPercent']}% / {compact_number(campaign['kpiTarget'])}",
                f"  So ngay con lai: {campaign['daysLeft']}",
                "  *Video TikTok noi bat trong 2 ngay gan day:*",
            ]
        )
        if campaign.get("topRecentTikTok"):
            for index, item in enumerate(campaign["topRecentTikTok"], start=1):
                lines.append(f"  {index}. {item['channelName']} | {compact_number(item['view'])} view")
                lines.append(f"     {item['url']}")
        else:
            lines.append("  - Chua co du lieu.")
    return lines


def render_topf(section: dict[str, Any]) -> list[str]:
    lines = [
        "**Diem nhanh kenh Official**",
        f"*Top view 3 ngay: `{section['topWindow']['from']} -> {section['topWindow']['to']}`*",
    ]
    lines.extend(render_ranked_posts(section.get("topVideos", [])))
    lines.append("")
    lines.append(f"*Tong hop 7 ngay: `{section['summaryWindow']['from']} -> {section['summaryWindow']['to']}`*")
    for platform, totals in section.get("platformTotals", {}).items():
        lines.append(
            f"- {platform.title()}: {compact_number(totals['totalViews'])} view | {totals['totalClips']} clip"
        )
    return lines


def render_ranked_posts(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- Chua co du lieu."]
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item['channelName']} | {compact_number(item['view'])} view")
        lines.append(f"   {item['url']}")
    return lines


def compact_number(value: int) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)
