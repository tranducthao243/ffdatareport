from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .common import KOL_PLATFORMS, build_anchor_window, daily_totals, filter_posts, load_posts


def analyze_tope(
    db_path: Path,
    *,
    mode: str = "complete_previous_day",
    timezone_name: str,
    now: datetime | None = None,
) -> dict:
    posts = load_posts(db_path)
    start_date, end_date = build_anchor_window("7D", mode=mode, timezone_name=timezone_name, now=now)
    scoped = filter_posts(
        posts,
        start_date=start_date,
        end_date=end_date,
        platforms=KOL_PLATFORMS,
        require_kol=True,
    )
    return {
        "code": "TOPE",
        "title": "TOPE",
        "window": {"from": start_date.isoformat(), "to": end_date.isoformat()},
        "totalViews": sum(post.view for post in scoped),
        "totalClips": len(scoped),
        "daily": daily_totals(scoped),
    }
