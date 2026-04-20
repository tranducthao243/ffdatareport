from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .common import KOL_PLATFORMS, average, build_days_window, filter_posts, load_posts, percentage, rank_posts


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
        require_kol=True,
        hashtag_whitelist=tags,
    )
    top_start, top_end = build_days_window(3, mode=mode, timezone_name=timezone_name, now=now)
    top_recent = [
        post
        for post in scoped
        if top_start <= post.published_date <= top_end and post.platform == "tiktok"
    ]
    total_views = sum(post.view for post in scoped)
    total_clips = len(scoped)
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
    return {
        "code": "TOPD",
        "title": "TOPD",
        "campaignName": campaign["name"],
        "hashtags": sorted(tags),
        "window": {"from": campaign["start_date"], "to": campaign["end_date"]},
        "totalViews": total_views,
        "totalClips": total_clips,
        "topRecentTikTok": rank_posts(top_recent, limit=limit),
        "kpiTarget": target,
        "kpiPercent": percentage(total_views, target),
        "averageViewPerClip": average_view_per_clip,
        "averageDailyView": round(average_daily_view, 2),
        "forecastViewAtEnd": projected_with_buffer,
        "forecastKpiText": kpiForecast,
        "daysLeft": days_left,
        "coverageWarning": coverage_warning,
        "daysElapsed": days_elapsed,
    }
