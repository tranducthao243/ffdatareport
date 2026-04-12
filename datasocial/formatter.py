from __future__ import annotations

import json


def render_report(report: dict) -> str:
    if "modules" not in report:
        return render_legacy_report(report)

    meta = report["meta"]
    summary = report["summary"]
    modules = report["modules"]
    lines = [
        "Datasocial Report",
        f"generatedAt: {report['generatedAt']}",
        f"timezone: {meta['timezone']}",
        f"mode: {meta['windowMode']}",
        (
            "fetchWindow: "
            f"{meta['fetchWindow']['start_date']} -> {meta['fetchWindow']['end_date']} "
            f"({meta['fetchWindow']['label']})"
        ),
        f"summary: {json.dumps(summary, ensure_ascii=False)}",
        "",
        "Top Content By Platform (top 5 clips by views in the last 1 day):",
    ]
    for platform in ("tiktok", "youtube"):
        lines.append(f"  {platform}:")
        lines.extend(render_content_block(modules["topContentByPlatform"]["1D"][platform], indent="    "))

    lines.extend(["", "Trend Videos 7D (clips with unusually high views vs the same channel in the last 7 days):"])
    lines.extend(render_trend_block(modules["trendVideos7D"]))

    lines.extend(["", "Daily Views 7D (highest and lowest total system views in the last 7 days):"])
    lines.extend(render_daily_summary(modules["dailyViews7D"]))

    lines.extend(["", "Daily Post Count 7D (highest and lowest total published clips in the last 7 days):"])
    lines.extend(render_daily_post_summary(modules["dailyPostCount7D"]))

    lines.extend(["", "Top KOLs 7D (top 5 channels by total views in the last 7 days):"])
    for platform in ("tiktok", "youtube"):
        lines.append(f"  {platform}:")
        lines.extend(render_kol_block(modules["topKols7D"][platform], indent="    "))

    lines.extend(["", "Overview 7D (overall system totals in the last 7 days, no hashtag filter):"])
    lines.extend(render_overview(modules["overview7D"]))

    lines.extend(["", "Campaign Tracking:"])
    lines.append(f"- {modules['campaignTracking']['note']}")
    return "\n".join(lines)


def render_seatalk_report(report: dict, *, title: str = "Datasocial Report") -> str:
    if "modules" not in report:
        return render_legacy_seatalk_report(report, title=title)

    meta = report["meta"]
    summary = report["summary"]
    modules = report["modules"]
    lines = [
        f"**{title}**",
        f"Daily FFVN creator performance report for `{meta['fetchWindow']['start_date']} -> {meta['fetchWindow']['end_date']}`.",
        "",
        "**Top Content 1D**",
        "_Top 5 clips by views in the last 1 day._",
    ]
    lines.extend(render_seatalk_platform_block(modules["topContentByPlatform"]["1D"]))
    lines.extend(["", "**Trend Videos 7D**", "_Clips with unusually high views vs the same channel in the last 7 days._"])
    lines.extend(render_seatalk_trend_block(modules["trendVideos7D"]))
    lines.extend(["", "**Daily Views 7D**", "_Highest and lowest total system views in the last 7 days._"])
    lines.extend(render_seatalk_daily_summary(modules["dailyViews7D"], suffix="views"))
    lines.extend(["", "**Daily Posts 7D**", "_Highest and lowest total published clips in the last 7 days._"])
    lines.extend(render_seatalk_daily_post_summary(modules["dailyPostCount7D"], suffix="posts"))
    lines.extend(["", "**Top KOLs 7D**", "_Top 5 channels by total views in the last 7 days._"])
    lines.extend(render_seatalk_kol_block(modules["topKols7D"]))
    lines.extend(["", "**Overview 7D**", "_Overall system totals in the last 7 days, without hashtag filtering._"])
    lines.extend(render_seatalk_overview(modules["overview7D"]))
    return "\n".join(lines)


def render_content_block(items: list[dict], *, indent: str = "") -> list[str]:
    if not items:
        return [f"{indent}- No data"]
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        lines.append(f"{indent}{index}. {item['channelName'] or '-'} | view={item['view']} | {item['title']}")
        lines.append(f"{indent}   url: {item['url']}")
    return lines


def render_trend_block(items: list[dict]) -> list[str]:
    if not items:
        return ["- No data"]
    return [
        f"{index}. {item['channelName'] or '-'} | view={item['view']} | {item['url']}"
        for index, item in enumerate(items, start=1)
    ]


def render_daily_summary(section: dict) -> list[str]:
    return [
        f"- highest={section['peakDate']} ({section['peakValue']})",
        f"- lowest={section['lowDate']} ({section['lowValue']})",
        f"- peakPostingHour={section['peakPostingHourRange']} ({section['peakPostingHourCount']} clips)",
    ]


def render_daily_post_summary(section: dict) -> list[str]:
    return [
        f"- highest={section['peakDate']} ({section['peakValue']})",
        f"- lowest={section['lowDate']} ({section['lowValue']})",
    ]


def render_kol_block(items: list[dict], *, indent: str = "") -> list[str]:
    if not items:
        return [f"{indent}- No data"]
    return [
        f"{indent}{index}. {item['channelName'] or '-'} | totalView={item['totalView']} | posts={item['postCount']}"
        for index, item in enumerate(items, start=1)
    ]


def render_overview(section: dict) -> list[str]:
    return [
        f"- totalView={section['totalView']}",
        f"- totalPosts={section['totalPosts']}",
        f"- averageView={section['averageView']}",
    ]


def render_seatalk_platform_block(section: dict[str, list[dict]]) -> list[str]:
    lines = ["TT:"]
    lines.extend(render_seatalk_compact_items(section.get("tiktok", [])))
    lines.append("YT:")
    lines.extend(render_seatalk_compact_items(section.get("youtube", [])))
    return lines


def render_seatalk_compact_items(items: list[dict]) -> list[str]:
    if not items:
        return ["- No data"]
    return [
        f"{index}. {truncate(item.get('channelName') or '-', 20)} | {format_number(item.get('view', 0))} | [Link]({item.get('url')})"
        for index, item in enumerate(items, start=1)
    ]


def render_seatalk_trend_block(items: list[dict]) -> list[str]:
    if not items:
        return ["- No data"]
    return [
        f"{index}. {truncate(item['channelName'] or '-', 20)} | {format_number(item['view'])} | [Link]({item.get('url')})"
        for index, item in enumerate(items, start=1)
    ]


def render_seatalk_daily_summary(section: dict, *, suffix: str) -> list[str]:
    return [
        f"- Highest: {section['peakDate']} | {format_number(section['peakValue'])} {suffix}",
        f"- Lowest: {section['lowDate']} | {format_number(section['lowValue'])} {suffix}",
        f"- Peak posting hour: {section['peakPostingHourRange']} | {section['peakPostingHourCount']} clips",
    ]


def render_seatalk_daily_post_summary(section: dict, *, suffix: str) -> list[str]:
    return [
        f"- Highest: {section['peakDate']} | {format_number(section['peakValue'])} {suffix}",
        f"- Lowest: {section['lowDate']} | {format_number(section['lowValue'])} {suffix}",
    ]


def render_seatalk_kol_block(section: dict[str, list[dict]]) -> list[str]:
    lines = ["TikTok:"]
    lines.extend(render_seatalk_kols(section.get("tiktok", [])))
    lines.append("YouTube:")
    lines.extend(render_seatalk_kols(section.get("youtube", [])))
    return lines


def render_seatalk_kols(items: list[dict]) -> list[str]:
    if not items:
        return ["- No data"]
    return [
        f"{index}. {truncate(item['channelName'] or '-', 22)}"
        f" | views {format_number(item['totalView'])}"
        f" | clips {item['postCount']}"
        for index, item in enumerate(items, start=1)
    ]


def render_seatalk_overview(section: dict) -> list[str]:
    return [
        f"- Total views: {format_number(section['totalView'])}",
        f"- Total clips: {section['totalPosts']}",
        f"- Avg view: {format_number(section['averageView'])}",
    ]


def format_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def render_legacy_report(report: dict) -> str:
    lines = [
        "Datasocial Report",
        f"generatedAt: {report['generatedAt']}",
        f"summary: {json.dumps(report['summary'], ensure_ascii=False)}",
    ]
    return "\n".join(lines)


def render_legacy_seatalk_report(report: dict, *, title: str) -> str:
    summary = report.get("summary", {})
    return "\n".join(
        [
            f"**{title}**",
            f"- Generated: `{report.get('generatedAt', '-')}`",
            (
                f"- Summary: fetched={summary.get('totalRowsFetched', summary.get('totalPostsFetched', '-'))}, "
                f"after_filter={summary.get('totalRowsAfterFilters', summary.get('totalPostsAfterHashtagFilter', '-'))}"
            ),
        ]
    )
