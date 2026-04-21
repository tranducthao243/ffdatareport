from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .common import (
    ROBLOX_CATEGORY_IDS,
    build_anchor_window,
    filter_posts,
    load_posts,
    rank_posts_limited_per_channel,
    summarize_channels_by_platform,
)


ROBLOX_PLATFORMS = ("tiktok", "youtube")


def analyze_toph(
    db_path: Path,
    *,
    mode: str = "complete_previous_day",
    timezone_name: str,
    now: datetime | None = None,
    video_limit: int = 10,
    channel_limit: int = 5,
) -> dict:
    posts = load_posts(db_path)
    week_start, week_end = build_anchor_window("7D", mode=mode, timezone_name=timezone_name, now=now)
    weekly_posts = filter_posts(
        posts,
        start_date=week_start,
        end_date=week_end,
        platforms=ROBLOX_PLATFORMS,
        category_ids=ROBLOX_CATEGORY_IDS,
    )

    top_videos_by_platform = {
        platform: rank_posts_limited_per_channel(
            (post for post in weekly_posts if post.platform == platform),
            limit=video_limit,
            per_channel_limit=2,
        )
        for platform in ROBLOX_PLATFORMS
    }

    top_channels_by_platform = summarize_channels_by_platform(
        weekly_posts,
        limit=channel_limit,
        platforms=ROBLOX_PLATFORMS,
    )

    return {
        "code": "TOPH",
        "title": "TOPH",
        "window": {"from": week_start.isoformat(), "to": week_end.isoformat()},
        "topVideosByPlatform": top_videos_by_platform,
        "topChannelsByPlatform": top_channels_by_platform,
    }
