from __future__ import annotations

import json
import sqlite3
import unicodedata
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from datasocial.exporter import parse_export_csv
from datasocial.timewindows import DEFAULT_REPORT_TZ, get_report_timezone


KOL_CATEGORY_IDS = {14, 22, 23, 24}
OFFICIAL_CATEGORY_IDS = {13}
PLATFORM_NAME_MAP = {
    "tiktok": "tiktok",
    "tik tok": "tiktok",
    "youtube": "youtube",
    "facebook": "facebook",
}
OFFICIAL_CATEGORY_NAME_HINTS = {"official", "nha phat hanh", "nph"}


@dataclass(slots=True)
class NormalizedPost:
    post_id: str
    row_id: str
    platform: str
    channel_id: str
    channel_name: str
    category_id: int | None
    category_name: str
    post_type: str
    title: str
    description: str
    url: str
    published_at: str
    published_date: str
    published_ts: int
    view: int
    engagement: int
    reaction: int
    comment: int
    duration_seconds: int
    hashtags: list[str]
    raw_json: str


def build_sqlite_store(
    csv_path: Path,
    db_path: Path,
    *,
    timezone_name: str = DEFAULT_REPORT_TZ,
) -> dict[str, Any]:
    rows = parse_export_csv(csv_path.read_bytes())
    posts = [normalize_row(row, timezone_name=timezone_name) for row in rows]
    posts = [post for post in posts if post is not None]

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        ensure_schema(conn)
        conn.execute("DELETE FROM post_hashtags")
        conn.execute("DELETE FROM posts")
        for post in posts:
            upsert_post(conn, post)
        conn.commit()
    return sqlite_store_summary(db_path)


def sqlite_store_summary(db_path: Path) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        counts = conn.execute(
            """
            SELECT
              COUNT(*) AS post_count,
              COUNT(DISTINCT channel_id) AS channel_count,
              COALESCE(SUM(view), 0) AS total_view
            FROM posts
            """
        ).fetchone()
        platform_rows = conn.execute(
            """
            SELECT platform, COUNT(*) AS post_count
            FROM posts
            GROUP BY platform
            ORDER BY platform
            """
        ).fetchall()
    return {
        "dbPath": str(db_path),
        "postCount": int(counts["post_count"]),
        "channelCount": int(counts["channel_count"]),
        "totalView": int(counts["total_view"]),
        "platformCounts": {row["platform"]: int(row["post_count"]) for row in platform_rows},
    }


def normalize_row(row: dict[str, str], *, timezone_name: str) -> NormalizedPost | None:
    published_at = parse_publish_time(row.get("Publish time") or "", timezone_name=timezone_name)
    post_id = (row.get("Post id") or "").strip()
    url = (row.get("Link") or "").strip()
    if not published_at or not post_id:
        return None

    platform = normalize_platform(row.get("Platform") or "")
    category_name = (row.get("Category") or "").strip()
    category_id = parse_int(row.get("__category_id"))
    title = clean_title(row.get("Post description") or "")
    hashtags = normalize_hashtags(row.get("Hashtag") or "")

    if category_id is None:
        category_id = infer_category_id(category_name)

    return NormalizedPost(
        post_id=post_id,
        row_id=(row.get("ID") or "").strip(),
        platform=platform,
        channel_id=(row.get("Channel id") or "").strip(),
        channel_name=(row.get("Channel name") or "").strip(),
        category_id=category_id,
        category_name=category_name,
        post_type=(row.get("Post type") or "").strip(),
        title=title,
        description=(row.get("Post description") or "").strip(),
        url=url,
        published_at=published_at.isoformat(),
        published_date=published_at.date().isoformat(),
        published_ts=int(published_at.timestamp()),
        view=parse_int(row.get("View")) or 0,
        engagement=parse_int(row.get("Engagement")) or 0,
        reaction=parse_int(row.get("Reaction")) or 0,
        comment=parse_int(row.get("Comment")) or 0,
        duration_seconds=parse_int(row.get("Duration (second)")) or 0,
        hashtags=hashtags,
        raw_json=json.dumps(row, ensure_ascii=False),
    )


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS posts (
            post_id TEXT PRIMARY KEY,
            row_id TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL,
            channel_id TEXT NOT NULL DEFAULT '',
            channel_name TEXT NOT NULL DEFAULT '',
            category_id INTEGER,
            category_name TEXT NOT NULL DEFAULT '',
            post_type TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            published_at TEXT NOT NULL,
            published_date TEXT NOT NULL,
            published_ts INTEGER NOT NULL,
            view INTEGER NOT NULL DEFAULT 0,
            engagement INTEGER NOT NULL DEFAULT 0,
            reaction INTEGER NOT NULL DEFAULT 0,
            comment INTEGER NOT NULL DEFAULT 0,
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            is_kol INTEGER NOT NULL DEFAULT 0,
            is_official INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL DEFAULT '{}',
            inserted_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS post_hashtags (
            post_id TEXT NOT NULL,
            hashtag TEXT NOT NULL,
            PRIMARY KEY (post_id, hashtag),
            FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_posts_published_ts ON posts(published_ts);
        CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform);
        CREATE INDEX IF NOT EXISTS idx_posts_category_id ON posts(category_id);
        CREATE INDEX IF NOT EXISTS idx_posts_channel_id ON posts(channel_id);
        CREATE INDEX IF NOT EXISTS idx_post_hashtags_hashtag ON post_hashtags(hashtag);
        """
    )


def upsert_post(conn: sqlite3.Connection, post: NormalizedPost) -> None:
    inserted_at = datetime.utcnow().isoformat()
    is_kol = 1 if post.category_id in KOL_CATEGORY_IDS or (post.category_id is None and not is_official_name(post.category_name)) else 0
    is_official = 1 if post.category_id in OFFICIAL_CATEGORY_IDS or is_official_name(post.category_name) else 0
    conn.execute(
        """
        INSERT INTO posts (
            post_id, row_id, platform, channel_id, channel_name, category_id, category_name,
            post_type, title, description, url, published_at, published_date, published_ts,
            view, engagement, reaction, comment, duration_seconds, is_kol, is_official,
            raw_json, inserted_at
        ) VALUES (
            :post_id, :row_id, :platform, :channel_id, :channel_name, :category_id, :category_name,
            :post_type, :title, :description, :url, :published_at, :published_date, :published_ts,
            :view, :engagement, :reaction, :comment, :duration_seconds, :is_kol, :is_official,
            :raw_json, :inserted_at
        )
        ON CONFLICT(post_id) DO UPDATE SET
            row_id=excluded.row_id,
            platform=excluded.platform,
            channel_id=excluded.channel_id,
            channel_name=excluded.channel_name,
            category_id=excluded.category_id,
            category_name=excluded.category_name,
            post_type=excluded.post_type,
            title=excluded.title,
            description=excluded.description,
            url=excluded.url,
            published_at=excluded.published_at,
            published_date=excluded.published_date,
            published_ts=excluded.published_ts,
            view=excluded.view,
            engagement=excluded.engagement,
            reaction=excluded.reaction,
            comment=excluded.comment,
            duration_seconds=excluded.duration_seconds,
            is_kol=excluded.is_kol,
            is_official=excluded.is_official,
            raw_json=excluded.raw_json,
            inserted_at=excluded.inserted_at
        """,
        {
            **asdict(post),
            "is_kol": is_kol,
            "is_official": is_official,
            "inserted_at": inserted_at,
        },
    )
    conn.execute("DELETE FROM post_hashtags WHERE post_id = ?", (post.post_id,))
    conn.executemany(
        "INSERT OR IGNORE INTO post_hashtags (post_id, hashtag) VALUES (?, ?)",
        [(post.post_id, hashtag) for hashtag in post.hashtags],
    )


def parse_publish_time(value: str, *, timezone_name: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    timezone = get_report_timezone(timezone_name)
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone)
    except ValueError:
        return None


def normalize_platform(value: str) -> str:
    key = compact_text(value)
    return PLATFORM_NAME_MAP.get(key, key or "unknown")


def normalize_hashtags(text: str) -> list[str]:
    tokens = [token.strip() for token in text.replace("\n", " ").split() if token.strip()]
    hashtags: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if not token.startswith("#"):
            continue
        normalized = compact_text(token.lstrip("#").rstrip(",.;:!?)("))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        hashtags.append(normalized)
    return hashtags


def infer_category_id(category_name: str) -> int | None:
    if is_official_name(category_name):
        return 13
    return None


def is_official_name(category_name: str) -> bool:
    compact = compact_text(category_name)
    return any(hint in compact for hint in OFFICIAL_CATEGORY_NAME_HINTS)


def compact_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(ascii_text.strip().lower().split())


def clean_title(value: str) -> str:
    first_line = next((line.strip() for line in value.splitlines() if line.strip()), "")
    compact = " ".join(first_line.split())
    if len(compact) <= 160:
        return compact
    return compact[:159] + "..."


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None
