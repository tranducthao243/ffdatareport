from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from datasocial.timewindows import DEFAULT_REPORT_TZ, build_date_window, get_report_timezone


KOL_WHITELIST = {"freefire", "nhasangtaofreefire", "ff", "garena"}
KOL_PLATFORMS = ("tiktok", "youtube")
OFFICIAL_PLATFORMS = ("tiktok", "youtube", "facebook")


@dataclass(slots=True)
class StorePost:
    post_id: str
    platform: str
    channel_id: str
    channel_name: str
    category_id: int | None
    category_name: str
    title: str
    description: str
    url: str
    published_at: datetime
    published_date: date
    view: int
    engagement: int
    reaction: int
    comment: int
    duration_seconds: int
    is_kol: bool
    is_official: bool
    hashtags: list[str]


def load_posts(db_path: Path) -> list[StorePost]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        post_rows = conn.execute(
            """
            SELECT
              post_id, platform, channel_id, channel_name, category_id, category_name,
              title, description, url, published_at, published_date,
              view, engagement, reaction, comment, duration_seconds,
              is_kol, is_official
            FROM posts
            """
        ).fetchall()
        hashtag_rows = conn.execute(
            "SELECT post_id, hashtag FROM post_hashtags ORDER BY post_id, hashtag"
        ).fetchall()

    hashtags_map: dict[str, list[str]] = {}
    for row in hashtag_rows:
        hashtags_map.setdefault(row["post_id"], []).append(row["hashtag"])

    posts: list[StorePost] = []
    for row in post_rows:
        published_at = datetime.fromisoformat(row["published_at"])
        posts.append(
            StorePost(
                post_id=row["post_id"],
                platform=row["platform"],
                channel_id=row["channel_id"],
                channel_name=row["channel_name"],
                category_id=row["category_id"],
                category_name=row["category_name"],
                title=row["title"],
                description=row["description"],
                url=row["url"],
                published_at=published_at,
                published_date=published_at.date(),
                view=int(row["view"]),
                engagement=int(row["engagement"]),
                reaction=int(row["reaction"]),
                comment=int(row["comment"]),
                duration_seconds=int(row["duration_seconds"]),
                is_kol=bool(row["is_kol"]),
                is_official=bool(row["is_official"]),
                hashtags=hashtags_map.get(row["post_id"], []),
            )
        )
    return posts


def build_anchor_window(
    label: str,
    *,
    mode: str,
    timezone_name: str,
    now: datetime | None = None,
) -> tuple[date, date]:
    window = build_date_window(label, mode=mode, timezone_name=timezone_name, now=now)
    return date.fromisoformat(window.start_date), date.fromisoformat(window.end_date)


def build_days_window(
    days: int,
    *,
    mode: str,
    timezone_name: str,
    now: datetime | None = None,
) -> tuple[date, date]:
    tz = get_report_timezone(timezone_name)
    local_now = (now or datetime.now(tz)).astimezone(tz)
    anchor = local_now.date() - timedelta(days=1) if mode == "complete_previous_day" else local_now.date()
    start = anchor - timedelta(days=days - 1)
    return start, anchor


def filter_posts(
    posts: Iterable[StorePost],
    *,
    start_date: date,
    end_date: date,
    platforms: tuple[str, ...] | None = None,
    require_kol: bool = False,
    require_official: bool = False,
    hashtag_whitelist: set[str] | None = None,
) -> list[StorePost]:
    results: list[StorePost] = []
    for post in posts:
        if post.published_date < start_date or post.published_date > end_date:
            continue
        if platforms and post.platform not in platforms:
            continue
        if require_kol and not post.is_kol:
            continue
        if require_official and not post.is_official:
            continue
        if hashtag_whitelist and not (set(post.hashtags) & hashtag_whitelist):
            continue
        results.append(post)
    return results


def serialize_post(post: StorePost) -> dict[str, Any]:
    return {
        "postId": post.post_id,
        "platform": post.platform,
        "channelId": post.channel_id,
        "channelName": post.channel_name,
        "categoryId": post.category_id,
        "categoryName": post.category_name,
        "title": post.title,
        "url": post.url,
        "publishedAt": post.published_at.isoformat(),
        "view": post.view,
        "engagement": post.engagement,
        "reaction": post.reaction,
        "comment": post.comment,
        "hashtags": post.hashtags,
    }


def rank_posts(posts: Iterable[StorePost], *, limit: int) -> list[dict[str, Any]]:
    ranked = sorted(posts, key=lambda post: (post.view, post.engagement), reverse=True)[:limit]
    return [serialize_post(post) for post in ranked]


def summarize_channels(posts: Iterable[StorePost], *, limit: int) -> list[dict[str, Any]]:
    channels: dict[tuple[str, str, str], dict[str, Any]] = {}
    for post in posts:
        key = (post.platform, post.channel_id, post.channel_name)
        entry = channels.setdefault(
            key,
            {
                "platform": post.platform,
                "channelId": post.channel_id,
                "channelName": post.channel_name,
                "totalView": 0,
                "totalClips": 0,
            },
        )
        entry["totalView"] += post.view
        entry["totalClips"] += 1
    return sorted(
        channels.values(),
        key=lambda item: (item["totalView"], item["totalClips"]),
        reverse=True,
    )[:limit]


def daily_totals(posts: Iterable[StorePost]) -> list[dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for post in posts:
        key = post.published_date.isoformat()
        entry = values.setdefault(key, {"date": key, "totalView": 0, "totalClips": 0})
        entry["totalView"] += post.view
        entry["totalClips"] += 1
    return [values[key] for key in sorted(values.keys())]


def percentage(value: int, target: int) -> float:
    if target <= 0:
        return 0.0
    return round((value / target) * 100, 2)
