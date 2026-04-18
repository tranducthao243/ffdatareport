from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .common import KOL_PLATFORMS, build_days_window, filter_posts, load_posts, percentage, rank_posts


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
    top_start, top_end = build_days_window(2, mode=mode, timezone_name=timezone_name, now=now)
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
        "daysLeft": days_left,
    }
