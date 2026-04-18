from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .common import KOL_PLATFORMS, KOL_WHITELIST, build_days_window, filter_posts, load_posts, rank_posts


def analyze_topa(
    db_path: Path,
    *,
    mode: str = "complete_previous_day",
    timezone_name: str,
    now: datetime | None = None,
    limit: int = 5,
) -> dict:
    posts = load_posts(db_path)
    start_date, end_date = build_days_window(2, mode=mode, timezone_name=timezone_name, now=now)
    scoped = filter_posts(
        posts,
        start_date=start_date,
        end_date=end_date,
        platforms=KOL_PLATFORMS,
        require_kol=True,
        hashtag_whitelist=KOL_WHITELIST,
    )
    return {
        "code": "TOPA",
        "title": "TOPA",
        "window": {"from": start_date.isoformat(), "to": end_date.isoformat()},
        "tiktok": rank_posts([post for post in scoped if post.platform == "tiktok"], limit=limit),
        "youtube": rank_posts([post for post in scoped if post.platform == "youtube"], limit=limit),
    }
