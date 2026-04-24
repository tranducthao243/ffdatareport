from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def render_seatalk_package(package: dict[str, Any]) -> str:
    lines = [
        f"**{str(package['title']).strip()}**",
        f"*Bản tóm tắt dữ liệu tự động | Gói dữ liệu: `{package['reportCode']}`*",
        "",
    ]
    for section in package.get("sections", []):
        code = str(section.get("code") or "").strip()
        if code == "TOPA":
            lines.extend(render_top_by_platform("Video nổi bật trong 24 giờ qua", section))
        elif code == "TOPB":
            lines.extend(render_top_by_platform("Video nổi bật trong 7 ngày qua", section))
        elif code == "TOPC":
            lines.extend(render_top_channels("5 kênh KOL nổi bật trong 7 ngày qua", section))
        elif code == "TOPE":
            lines.extend(render_tope(section))
        elif code == "TOPD":
            lines.extend(render_topd(section))
        elif code == "TOPF":
            lines.extend(render_topf(section))
        elif code == "TOPG":
            lines.extend(render_topg(section))
        elif code == "TOPH":
            lines.extend(render_toph(section))
        lines.append("")
    return "\n".join(line for line in lines if line is not None).strip()


def render_top_by_platform(title: str, section: dict[str, Any]) -> list[str]:
    lines = [
        f"**{title}**",
        f"*Khung thời gian: `{section['window']['from']} -> {section['window']['to']}`*",
        "",
        "*TikTok*",
    ]
    lines.extend(render_ranked_posts(section.get("tiktok", [])))
    lines.append("")
    lines.append("*YouTube*")
    lines.extend(render_ranked_posts(section.get("youtube", [])))
    return lines


def render_top_channels(title: str, section: dict[str, Any]) -> list[str]:
    lines = [f"**{title}**", f"*Khung thời gian: `{section['window']['from']} -> {section['window']['to']}`*"]
    for index, item in enumerate(section.get("channels", []), start=1):
        lines.append(
            f"{index}. {item['channelName']} | {compact_number(item['totalView'])} view | {item['totalClips']} clip"
        )
    if len(lines) == 2:
        lines.append("- Chưa có dữ liệu.")
    return lines


def render_tope(section: dict[str, Any]) -> list[str]:
    history_compare = section.get("historyCompare") or {}
    lines = [
        "**Tổng quan data KOL 7 ngày qua**",
        f"*Khung thời gian: `{section['window']['from']} -> {section['window']['to']}`*",
        f"- Tổng view: {compact_number(section['totalViews'])}",
        f"- Tổng clip: {section['totalClips']}",
    ]
    daily = list(section.get("daily") or [])
    if len(daily) >= 2:
        current_day = str(daily[-1].get("date", "-"))
        previous_day = str(daily[-2].get("date", "-"))
        current_day_views = int(daily[-1].get("totalView", 0) or 0)
        previous_day_views = int(daily[-2].get("totalView", 0) or 0)
        lines.append(
            f"- View ngày {current_day} so với ngày {previous_day}: {format_delta(current_day_views - previous_day_views)}"
        )
    if history_compare.get("vsPreviousWeek"):
        current_from = _parse_iso_date(section.get("window", {}).get("from"))
        current_to = _parse_iso_date(section.get("window", {}).get("to"))
        previous_from = current_from - timedelta(days=7) if current_from else None
        previous_to = current_to - timedelta(days=7) if current_to else None
        lines.append(
            f"- Tổng view giai đoạn `{section['window']['from']} -> {section['window']['to']}`"
            f" so với giai đoạn `{_format_window_date(previous_from)} -> {_format_window_date(previous_to)}`"
            f": {format_delta(int(history_compare['vsPreviousWeek']['views']['change']))}"
        )
        lines.append(
            f"- Tổng clip giai đoạn `{section['window']['from']} -> {section['window']['to']}`"
            f" so với giai đoạn `{_format_window_date(previous_from)} -> {_format_window_date(previous_to)}`"
            f": {format_delta(int(history_compare['vsPreviousWeek']['clips']['change']))}"
        )
    return lines


def _parse_iso_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _format_window_date(value: date | None) -> str:
    return value.isoformat() if value else "-"


def render_topd(section: dict[str, Any]) -> list[str]:
    lines = ["**=== CAMPAIGN REPORT ===**"]
    campaigns = section.get("campaigns", [])
    if not campaigns:
        return lines + ["- Chưa có campaign nào được gán cho nhóm này."]
    for campaign in campaigns:
        average_view_per_clip = campaign.get("averageViewPerClip", 0)
        official_contribution = campaign.get("officialContribution") or {}
        lines.extend(
            [
                "",
                f"**{campaign['campaignName']}** | {', '.join('#' + tag for tag in campaign['hashtags'])}",
                "",
                "**1. Overview**",
                f"- Tổng view: {compact_number(campaign['totalViews'])}",
                f"- Tổng clip: {campaign['totalClips']}",
                f"- KPI: {campaign['kpiPercent']}% / {compact_number(campaign['kpiTarget'])}",
                f"- Số ngày còn lại: {campaign['daysLeft']}",
                "",
                "**2. Content performance**",
                f"- Trung bình view / clip: {compact_number(int(average_view_per_clip))}",
                f"- Dự báo KPI: {campaign.get('forecastKpiText', '-')}",
                f"- So sánh với hôm qua: {format_history_view_change(campaign.get('historyCompare'), 'vsPreviousDay')}",
                "",
                "**3. Hashtag performance**",
                f"- Hashtags: {', '.join('#' + tag for tag in campaign['hashtags'])}",
                "Top TikTok 3 ngày gần đây:",
            ]
        )
        if campaign.get("coverageWarning"):
            lines.append(f"- Lưu ý coverage: {campaign['coverageWarning']}")
        if campaign.get("topRecentTikTok"):
            for index, item in enumerate(campaign["topRecentTikTok"], start=1):
                lines.append(f"{index}. {item['channelName']} | {compact_number(item['view'])} view")
                lines.append(f"   {item['url']}")
        else:
            lines.append("- Chưa có dữ liệu.")
        lines.extend(
            [
                "",
                "**4. Official contribution**",
                f"- Total views: {compact_number(int(official_contribution.get('totalViews', 0) or 0))}",
                f"- Total content: {int(official_contribution.get('totalClips', 0) or 0)}",
                f"- Percentage: {official_contribution.get('percentage', 0)}%",
                "",
                "**5. TOP KOLs chưa tham gia campaign**",
            ]
        )
        top_kols_without_campaign = campaign.get("topKolsWithoutCampaign", [])
        if top_kols_without_campaign:
            for index, item in enumerate(top_kols_without_campaign, start=1):
                lines.append(
                    f"{index}. {item['channelName']} | {compact_number(item['totalViews'])} view | {item['totalClips']} clip"
                )
        else:
            lines.append("- Không có KOL nổi bật nào đang nằm ngoài campaign.")
    return lines


def render_topf(section: dict[str, Any]) -> list[str]:
    lines = [
        "**Điểm nhanh kênh Official**",
        f"*Top 5 view 3 ngày: `{section['topWindow']['from']} -> {section['topWindow']['to']}`*",
    ]
    lines.extend(render_ranked_posts(section.get("topVideos", [])))
    lines.append("")
    lines.append(f"*Top 3 bài viết tương tác 3 ngày: `{section['topWindow']['from']} -> {section['topWindow']['to']}`*")
    top_photo_posts = section.get("topPhotoEngagement", [])
    if top_photo_posts:
        for index, item in enumerate(top_photo_posts, start=1):
            lines.append(f"{index}. {item['channelName']} | {compact_number(item['reaction'])} reaction")
            lines.append(f"   {item['url']}")
    else:
        lines.append("- Chưa có dữ liệu.")
    lines.append("")
    lines.append(f"- Tổng số bài viết trên fanpage 3 ngày qua: {section.get('totalFanpagePosts3D', 0)}")
    lines.append("")
    lines.append(f"*Tổng hợp 7 ngày: `{section['summaryWindow']['from']} -> {section['summaryWindow']['to']}`*")
    for platform, totals in section.get("platformTotals", {}).items():
        lines.append(
            f"- {platform.title()}: {compact_number(totals['totalViews'])} view | {totals['totalClips']} clip"
        )
    lines.extend(render_history_compare(section.get("historyCompare")))
    return lines


def render_topg(section: dict[str, Any]) -> list[str]:
    lines = [
        "**Trend nhảy**",
        f"*Top 10 video nhiều view nhất tuần: `{section['weekWindow']['from']} -> {section['weekWindow']['to']}`*",
    ]
    lines.extend(render_ranked_posts(section.get("topWeeklyVideos", [])))
    lines.append("")
    lines.append(f"*Top 10 video nhiều view nhất tháng qua: `{section['monthWindow']['from']} -> {section['monthWindow']['to']}`*")
    lines.extend(render_ranked_posts(section.get("topMonthlyVideos", [])))
    lines.append("")
    lines.append(f"*Top 10 kênh có tổng view nhiều nhất 30 ngày qua: `{section['monthWindow']['from']} -> {section['monthWindow']['to']}`*")
    lines.extend(render_ranked_channels(section.get("topMonthlyChannels", [])))
    return lines


def render_toph(section: dict[str, Any]) -> list[str]:
    lines = [
        "**Roblox Content**",
        f"*Top 10 video nhiều view nhất tuần: `{section['window']['from']} -> {section['window']['to']}`*",
    ]
    for platform in ("tiktok", "youtube"):
        lines.append("")
        lines.append(f"*{platform.title()}*")
        lines.extend(render_ranked_posts(section.get("topVideosByPlatform", {}).get(platform, [])))
    lines.append("")
    lines.append(f"*Top 5 kênh có tổng view nhiều nhất 7 ngày qua: `{section['window']['from']} -> {section['window']['to']}`*")
    for platform in ("tiktok", "youtube"):
        lines.append(f"- {platform.title()}:")
        lines.extend(render_ranked_channels(section.get("topChannelsByPlatform", {}).get(platform, []), indent="  "))
    return lines


def render_ranked_posts(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- Chưa có dữ liệu."]
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item['channelName']} | {compact_number(item['view'])} view")
        lines.append(f"   {item['url']}")
    return lines


def render_ranked_channels(items: list[dict[str, Any]], *, indent: str = "") -> list[str]:
    if not items:
        return [f"{indent}- Chưa có dữ liệu."]
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        lines.append(
            f"{indent}{index}. {item['channelName']} | {compact_number(item['totalView'])} view | {item['totalClips']} clip"
        )
    return lines


def compact_number(value: int) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def format_delta(change: int) -> str:
    if change > 0:
        return f"Tăng {compact_number(change)}"
    if change < 0:
        return f"Giảm {compact_number(abs(change))}"
    return "Không đổi"


def render_history_compare(history_compare: dict[str, Any] | None, *, include_clips: bool = True) -> list[str]:
    if not history_compare:
        return []
    lines: list[str] = []
    if "vsPreviousDay" in history_compare:
        current = history_compare["vsPreviousDay"]
        line = f"- So với hôm qua: view {format_delta(int(current['views']['change']))}"
        if include_clips:
            line += f" | clip {format_delta(int(current['clips']['change']))}"
        lines.append(line)
    if "vsPreviousWeek" in history_compare:
        current = history_compare["vsPreviousWeek"]
        line = f"- So với tuần trước: view {format_delta(int(current['views']['change']))}"
        if include_clips:
            line += f" | clip {format_delta(int(current['clips']['change']))}"
        lines.append(line)
    return lines


def format_history_view_change(history_compare: dict[str, Any] | None, key: str) -> str:
    if not history_compare or key not in history_compare:
        return "Không có dữ liệu"
    return format_delta(int(history_compare[key]["views"]["change"]))
