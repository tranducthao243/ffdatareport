from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .common import KOL_CATEGORY_IDS, KOL_PLATFORMS, build_anchor_window, filter_posts, load_posts, summarize_channels


def analyze_topc(
    db_path: Path,
    *,
    mode: str = "complete_previous_day",
    timezone_name: str,
    now: datetime | None = None,
    limit: int = 5,
) -> dict:
    posts = load_posts(db_path)
    start_date, end_date = build_anchor_window("7D", mode=mode, timezone_name=timezone_name, now=now)
    scoped = filter_posts(
        posts,
        start_date=start_date,
        end_date=end_date,
        platforms=KOL_PLATFORMS,
        category_ids=KOL_CATEGORY_IDS,
        require_kol=True,
    )
    return {
        "code": "TOPC",
        "title": "TOPC",
        "window": {"from": start_date.isoformat(), "to": end_date.isoformat()},
        "channels": summarize_channels(scoped, limit=limit),
    }
