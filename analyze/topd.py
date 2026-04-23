from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .common import (
    KOL_CATEGORY_IDS,
    KOL_PLATFORMS,
    OFFICIAL_PLATFORMS,
    average,
    build_days_window,
    filter_posts,
    load_posts,
    percentage,
    rank_posts,
)


def analyze_topd(
    db_path: Path,
    *,
    campaign: dict,
    mode: str = "complete_previous_day",
    timezone_name: str,
    now: datetime | None = None,
    limit: int = 5,
) -> dict:
    posts = load_posts(db_path)
    earliest_available_date = min((post.published_date for post in posts), default=None)
    tags = {str(tag).strip().lower().lstrip("#") for tag in campaign.get("hashtags", []) if str(tag).strip()}
    current_start = datetime.fromisoformat(campaign["start_date"]).date()
    current_end = datetime.fromisoformat(campaign["end_date"]).date()
    if now:
        current_end = min(current_end, (now.date() if now.tzinfo is None else now.astimezone().date()))

    scoped = filter_posts(
        posts,
        start_date=current_start,
        end_date=current_end,
        platforms=KOL_PLATFORMS,
        category_ids=KOL_CATEGORY_IDS,
        require_kol=True,
        hashtag_whitelist=tags,
    )
    top_start, top_end = build_days_window(3, mode=mode, timezone_name=timezone_name, now=now)
    top_recent = [
        post
        for post in scoped
        if top_start <= post.published_date <= top_end and post.platform == "tiktok"
    ]
    official_posts = [
        post
        for post in filter_posts(
            posts,
            start_date=current_start,
            end_date=current_end,
            platforms=OFFICIAL_PLATFORMS,
            hashtag_whitelist=tags,
        )
        if post.is_official or post.category_id == 13
    ]
    total_views = sum(post.view for post in scoped)
    total_clips = len(scoped)
    official_views = sum(post.view for post in official_posts)
    official_clips = len(official_posts)
    target = int(campaign.get("kpi_view_target", 0))
    today = (now or datetime.now()).date()
    days_left = max((datetime.fromisoformat(campaign["end_date"]).date() - today).days, 0)
    days_elapsed = max((today - current_start).days + 1, 1)
    average_view_per_clip = round(total_views / total_clips, 2) if total_clips else 0.0
    daily_views_map: dict[str, int] = {}
    for post in scoped:
        key = post.published_date.isoformat()
        daily_views_map[key] = daily_views_map.get(key, 0) + post.view
    average_daily_view = average(list(daily_views_map.values()))
    projected_end_view = int(total_views + average_daily_view * days_left)
    projected_with_buffer = int(projected_end_view * 1.2)
    projected_kpi_percent = percentage(projected_with_buffer, target)
    kpiForecast = "Da dat KPI" if total_views >= target and target > 0 else f"Du kien {projected_kpi_percent}% KPI"
    coverage_warning = ""
    if earliest_available_date and current_start < earliest_available_date:
        coverage_warning = (
            "Du lieu campaign co the chua day du vi ngay bat dau campaign nam ngoai cua so fetch hien tai."
        )
    kol_start, kol_end = build_days_window(7, mode=mode, timezone_name=timezone_name, now=now)
    recent_kol_posts = filter_posts(
        posts,
        start_date=kol_start,
        end_date=kol_end,
        platforms=KOL_PLATFORMS,
        category_ids=KOL_CATEGORY_IDS,
        require_kol=True,
    )
    non_participant_channels: dict[tuple[str, str, str], dict[str, object]] = {}
    for post in recent_kol_posts:
        key = (post.platform, post.channel_id, post.channel_name)
        entry = non_participant_channels.setdefault(
            key,
            {
                "platform": post.platform,
                "channelId": post.channel_id,
                "channelName": post.channel_name,
                "totalViews": 0,
                "totalClips": 0,
                "hasCampaignHashtag": False,
            },
        )
        entry["totalViews"] = int(entry["totalViews"]) + post.view
        entry["totalClips"] = int(entry["totalClips"]) + 1
        if set(post.hashtags) & tags:
            entry["hasCampaignHashtag"] = True
    top_kols_without_campaign = [
        {
            "platform": str(item["platform"]),
            "channelId": str(item["channelId"]),
            "channelName": str(item["channelName"]),
            "totalViews": int(item["totalViews"]),
            "totalClips": int(item["totalClips"]),
        }
        for item in sorted(
            (
                value
                for value in non_participant_channels.values()
                if not bool(value["hasCampaignHashtag"])
            ),
            key=lambda item: (int(item["totalViews"]), int(item["totalClips"])),
            reverse=True,
        )[:5]
    ]
    chart_start = today - timedelta(days=29)
    chart_posts = filter_posts(
        posts,
        start_date=chart_start,
        end_date=today,
        hashtag_whitelist=tags,
    )
    chart_daily: list[dict[str, object]] = []
    peak_day_channels: dict[tuple[str, str, str], dict[str, object]] = {}
    peak_day_total = -1
    peak_day_iso = ""
    for offset in range(30):
        day = chart_start + timedelta(days=offset)
        day_posts = [post for post in chart_posts if post.published_date == day]
        day_total = sum(post.view for post in day_posts)
        chart_daily.append({"date": day.isoformat(), "totalViews": day_total})
        if day_total > peak_day_total:
            peak_day_total = day_total
            peak_day_iso = day.isoformat()
            peak_day_channels = {}
            for post in day_posts:
                key = (post.platform, post.channel_id, post.channel_name)
                entry = peak_day_channels.setdefault(
                    key,
                    {"platform": post.platform, "channelName": post.channel_name, "totalViews": 0},
                )
                entry["totalViews"] = int(entry["totalViews"]) + post.view
    peak_day_top_channels = [
        {
            "platform": str(item["platform"]),
            "channelName": str(item["channelName"]),
            "totalViews": int(item["totalViews"]),
        }
        for item in sorted(
            peak_day_channels.values(),
            key=lambda item: (int(item["totalViews"]), str(item["channelName"])),
            reverse=True,
        )[:3]
    ]
    return {
        "code": "TOPD",
        "title": "TOPD",
        "campaignName": campaign["name"],
        "hashtags": sorted(tags),
        "window": {"from": campaign["start_date"], "to": campaign["end_date"]},
        "totalViews": total_views,
        "totalClips": total_clips,
        "topRecentTikTok": rank_posts(top_recent, limit=limit),
        "officialContribution": {
            "totalViews": official_views,
            "totalClips": official_clips,
            "percentage": percentage(official_views, total_views),
        },
        "dailyChart": chart_daily,
        "peakDay": {
            "date": peak_day_iso,
            "totalViews": max(peak_day_total, 0),
            "topChannels": peak_day_top_channels,
        },
        "kpiTarget": target,
        "kpiPercent": percentage(total_views, target),
        "averageViewPerClip": average_view_per_clip,
        "averageDailyView": round(average_daily_view, 2),
        "forecastViewAtEnd": projected_with_buffer,
        "forecastKpiText": kpiForecast,
        "daysLeft": days_left,
        "coverageWarning": coverage_warning,
        "daysElapsed": days_elapsed,
        "topKolsWithoutCampaignWindow": {"from": kol_start.isoformat(), "to": kol_end.isoformat()},
        "topKolsWithoutCampaign": top_kols_without_campaign,
    }
