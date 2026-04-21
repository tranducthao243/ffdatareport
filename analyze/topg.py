from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .common import (
    KOL_PLATFORMS,
    TREND_DANCE_CATEGORY_IDS,
    build_anchor_window,
    filter_posts,
    load_posts,
    rank_posts,
    summarize_channels,
)


def analyze_topg(
    db_path: Path,
    *,
    mode: str = "complete_previous_day",
    timezone_name: str,
    now: datetime | None = None,
    limit: int = 10,
) -> dict:
    posts = load_posts(db_path)
    week_start, week_end = build_anchor_window("7D", mode=mode, timezone_name=timezone_name, now=now)
    month_start, month_end = build_anchor_window("30D", mode=mode, timezone_name=timezone_name, now=now)

    weekly_posts = filter_posts(
        posts,
        start_date=week_start,
        end_date=week_end,
        platforms=KOL_PLATFORMS,
        category_ids=TREND_DANCE_CATEGORY_IDS,
    )
    monthly_posts = filter_posts(
        posts,
        start_date=month_start,
        end_date=month_end,
        platforms=KOL_PLATFORMS,
        category_ids=TREND_DANCE_CATEGORY_IDS,
    )

    return {
        "code": "TOPG",
        "title": "TOPG",
        "weekWindow": {"from": week_start.isoformat(), "to": week_end.isoformat()},
        "monthWindow": {"from": month_start.isoformat(), "to": month_end.isoformat()},
        "topWeeklyVideos": rank_posts(weekly_posts, limit=limit),
        "topMonthlyVideos": rank_posts(monthly_posts, limit=limit),
        "topMonthlyChannels": summarize_channels(monthly_posts, limit=limit),
    }
