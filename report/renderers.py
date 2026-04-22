from __future__ import annotations

from typing import Any


def render_seatalk_package(package: dict[str, Any]) -> str:
    lines = [
        f"**{str(package['title']).strip()}**",
        f"*Ban tom tat du lieu tu dong | Goi du lieu: `{package['reportCode']}`*",
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
        elif code == "TOPG":
            lines.extend(render_topg(section))
        elif code == "TOPH":
            lines.extend(render_toph(section))
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
    lines = [
        "**Tong quan hieu qua he KOL trong 7 ngay qua**",
        f"*Khung thoi gian: `{section['window']['from']} -> {section['window']['to']}`*",
        f"- Tong view: {compact_number(section['totalViews'])}",
        f"- Tong clip: {section['totalClips']}",
    ]
    history_compare = section.get("historyCompare") or {}
    daily = list(section.get("daily") or [])
    if len(daily) >= 2:
        today_views = int(daily[-1].get("totalView", 0) or 0)
        yesterday_views = int(daily[-2].get("totalView", 0) or 0)
        lines.append(f"- View hom nay so voi hom truoc: {format_delta(today_views - yesterday_views)}")
    if history_compare.get("vsPreviousWeek"):
        lines.append(
            "- View tuan nay so voi tuan truoc: "
            f"{format_delta(int(history_compare['vsPreviousWeek']['views']['change']))}"
        )
    lines.extend(render_history_compare(history_compare, include_clips=False))
    return lines


def render_topd(section: dict[str, Any]) -> list[str]:
    lines = ["**=== CAMPAIGN REPORT ===**"]
    campaigns = section.get("campaigns", [])
    if not campaigns:
        return lines + ["- Chua co campaign nao duoc gan cho nhom nay."]
    for campaign in campaigns:
        average_view_per_clip = campaign.get("averageViewPerClip", 0)
        lines.extend(
            [
                "",
                f"**{campaign['campaignName']}** | {', '.join('#' + tag for tag in campaign['hashtags'])}",
                "",
                "1. Overview",
                f"- Tong view: {compact_number(campaign['totalViews'])}",
                f"- Tong clip: {campaign['totalClips']}",
                f"- KPI: {campaign['kpiPercent']}% / {compact_number(campaign['kpiTarget'])}",
                f"- So ngay con lai: {campaign['daysLeft']}",
                "",
                "2. Content performance",
                f"- Trung binh view / clip: {compact_number(int(average_view_per_clip))}",
                f"- Du bao KPI: {campaign.get('forecastKpiText', '-')}",
                f"- So sanh voi hom qua: {format_history_view_change(campaign.get('historyCompare'), 'vsPreviousDay')}",
                "",
                "3. Hashtag performance",
                f"- Hashtags: {', '.join('#' + tag for tag in campaign['hashtags'])}",
                "Top TikTok 3 ngay gan day:",
            ]
        )
        if campaign.get("coverageWarning"):
            lines.append(f"- Luu y coverage: {campaign['coverageWarning']}")
        if campaign.get("topRecentTikTok"):
            for index, item in enumerate(campaign["topRecentTikTok"], start=1):
                lines.append(f"{index}. {item['channelName']} | {compact_number(item['view'])} view")
                lines.append(f"   {item['url']}")
        else:
            lines.append("- Chua co du lieu.")
        lines.extend(
            [
                "",
                "4. Official contribution",
                "- Official contribution data chua duoc tach rieng trong campaign analyzer hien tai.",
                (
                    "KOL noi bat 7 ngay qua chua tham gia campaign: "
                    f"`{campaign.get('topKolsWithoutCampaignWindow', {}).get('from', '-')}"
                    f" -> {campaign.get('topKolsWithoutCampaignWindow', {}).get('to', '-')}`"
                ),
            ]
        )
        top_kols_without_campaign = campaign.get("topKolsWithoutCampaign", [])
        if top_kols_without_campaign:
            for index, item in enumerate(top_kols_without_campaign, start=1):
                lines.append(
                    f"{index}. {item['channelName']} | {compact_number(item['totalViews'])} view | {item['totalClips']} clip"
                )
        else:
            lines.append("- Khong co KOL noi bat nao dang nam ngoai campaign.")
    return lines


def render_topf(section: dict[str, Any]) -> list[str]:
    lines = [
        "**Diem nhanh kenh Official**",
        f"*Top 5 view 3 ngay: `{section['topWindow']['from']} -> {section['topWindow']['to']}`*",
    ]
    lines.extend(render_ranked_posts(section.get("topVideos", [])))
    lines.append("")
    lines.append(f"*Top 3 bai viet tuong tac 3 ngay: `{section['topWindow']['from']} -> {section['topWindow']['to']}`*")
    top_photo_posts = section.get("topPhotoEngagement", [])
    if top_photo_posts:
        for index, item in enumerate(top_photo_posts, start=1):
            lines.append(f"{index}. {item['channelName']} | {compact_number(item['reaction'])} reaction")
            lines.append(f"   {item['url']}")
    else:
        lines.append("- Chua co du lieu.")
    lines.append("")
    lines.append(f"- Tong so bai viet tren fanpage 3 ngay qua: {section.get('totalFanpagePosts3D', 0)}")
    lines.append("")
    lines.append(f"*Tong hop 7 ngay: `{section['summaryWindow']['from']} -> {section['summaryWindow']['to']}`*")
    for platform, totals in section.get("platformTotals", {}).items():
        lines.append(
            f"- {platform.title()}: {compact_number(totals['totalViews'])} view | {totals['totalClips']} clip"
        )
    lines.extend(render_history_compare(section.get("historyCompare")))
    return lines


def render_topg(section: dict[str, Any]) -> list[str]:
    lines = [
        "**Trend nhay**",
        f"*Top 10 video nhieu view nhat tuan: `{section['weekWindow']['from']} -> {section['weekWindow']['to']}`*",
    ]
    lines.extend(render_ranked_posts(section.get("topWeeklyVideos", [])))
    lines.append("")
    lines.append(f"*Top 10 video nhieu view nhat thang qua: `{section['monthWindow']['from']} -> {section['monthWindow']['to']}`*")
    lines.extend(render_ranked_posts(section.get("topMonthlyVideos", [])))
    lines.append("")
    lines.append(f"*Top 10 kenh co tong view nhieu nhat 30 ngay qua: `{section['monthWindow']['from']} -> {section['monthWindow']['to']}`*")
    lines.extend(render_ranked_channels(section.get("topMonthlyChannels", [])))
    return lines


def render_toph(section: dict[str, Any]) -> list[str]:
    lines = [
        "**Roblox Content**",
        f"*Top 10 video nhieu view nhat tuan: `{section['window']['from']} -> {section['window']['to']}`*",
    ]
    for platform in ("tiktok", "youtube"):
        lines.append("")
        lines.append(f"*{platform.title()}*")
        lines.extend(render_ranked_posts(section.get("topVideosByPlatform", {}).get(platform, [])))
    lines.append("")
    lines.append(f"*Top 5 kenh co tong view nhieu nhat 7 ngay qua: `{section['window']['from']} -> {section['window']['to']}`*")
    for platform in ("tiktok", "youtube"):
        lines.append(f"- {platform.title()}:")
        lines.extend(render_ranked_channels(section.get("topChannelsByPlatform", {}).get(platform, []), indent="  "))
    return lines


def render_ranked_posts(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- Chua co du lieu."]
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item['channelName']} | {compact_number(item['view'])} view")
        lines.append(f"   {item['url']}")
    return lines


def render_ranked_channels(items: list[dict[str, Any]], *, indent: str = "") -> list[str]:
    if not items:
        return [f"{indent}- Chua co du lieu."]
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
        return f"Tang {compact_number(change)}"
    if change < 0:
        return f"Giam {compact_number(abs(change))}"
    return "Khong doi"


def render_history_compare(history_compare: dict[str, Any] | None, *, include_clips: bool = True) -> list[str]:
    if not history_compare:
        return []
    lines: list[str] = []
    if "vsPreviousDay" in history_compare:
        current = history_compare["vsPreviousDay"]
        line = f"- So voi hom qua: view {format_delta(int(current['views']['change']))}"
        if include_clips:
            line += f" | clip {format_delta(int(current['clips']['change']))}"
        lines.append(line)
    if "vsPreviousWeek" in history_compare:
        current = history_compare["vsPreviousWeek"]
        line = f"- So voi tuan truoc: view {format_delta(int(current['views']['change']))}"
        if include_clips:
            line += f" | clip {format_delta(int(current['clips']['change']))}"
        lines.append(line)
    return lines


def format_history_view_change(history_compare: dict[str, Any] | None, key: str) -> str:
    if not history_compare or key not in history_compare:
        return "Chua co du lieu so sanh"
    return format_delta(int(history_compare[key]["views"]["change"]))
