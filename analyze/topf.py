from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .common import OFFICIAL_PLATFORMS, build_anchor_window, build_days_window, filter_posts, load_posts, rank_posts


def analyze_topf(
    db_path: Path,
    *,
    mode: str = "complete_previous_day",
    timezone_name: str,
    now: datetime | None = None,
    limit: int = 5,
) -> dict:
    posts = load_posts(db_path)
    top_start, top_end = build_days_window(3, mode=mode, timezone_name=timezone_name, now=now)
    seven_start, seven_end = build_anchor_window("7D", mode=mode, timezone_name=timezone_name, now=now)
    top_posts = filter_posts(
        posts,
        start_date=top_start,
        end_date=top_end,
        platforms=OFFICIAL_PLATFORMS,
        require_official=True,
    )
    weekly_posts = filter_posts(
        posts,
        start_date=seven_start,
        end_date=seven_end,
        platforms=OFFICIAL_PLATFORMS,
        require_official=True,
    )
    totals_by_platform: dict[str, dict[str, int]] = {}
    for platform in OFFICIAL_PLATFORMS:
        scoped = [post for post in weekly_posts if post.platform == platform]
        totals_by_platform[platform] = {
            "totalViews": sum(post.view for post in scoped),
            "totalClips": len(scoped),
        }
    return {
        "code": "TOPF",
        "title": "TOPF",
        "topWindow": {"from": top_start.isoformat(), "to": top_end.isoformat()},
        "summaryWindow": {"from": seven_start.isoformat(), "to": seven_end.isoformat()},
        "topVideos": rank_posts(top_posts, limit=limit),
        "platformTotals": totals_by_platform,
    }
