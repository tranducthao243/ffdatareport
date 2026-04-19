from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from analyze.common import load_posts


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(ascii_text.strip().lower().split())


def compact_number(value: int) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


@dataclass(slots=True)
class QueryWindow:
    label: str
    start_date: date
    end_date: date


def resolve_query_window(question: str, *, now: datetime | None = None) -> QueryWindow:
    normalized = _normalize_text(question)
    today = (now or datetime.now()).date()
    if "hom nay" in normalized:
        return QueryWindow("hom nay", today, today)
    if "30 ngay" in normalized:
        return QueryWindow("30 ngay qua", today - timedelta(days=29), today)
    if "7 ngay" in normalized:
        return QueryWindow("7 ngay qua", today - timedelta(days=6), today)
    return QueryWindow("thang nay", today.replace(day=1), today)


def detect_query_metric(question: str) -> str | None:
    normalized = _normalize_text(question)
    if "clip trieu view" in normalized or "clip 1m" in normalized or "clip dat 1m" in normalized:
        return "million_view_clip_count"
    if "bao nhieu clip" in normalized or "dang bao nhieu clip" in normalized:
        return "clip_count"
    return None


def extract_channel_phrase(question: str) -> str:
    normalized = _normalize_text(question)
    patterns = [
        r"^(?P<channel>.+?) da dang bao nhieu clip(?: trong)? (?:thang nay|hom nay|7 ngay qua|30 ngay qua)$",
        r"^(?P<channel>.+?) (?:thang nay|hom nay|7 ngay qua|30 ngay qua) co bao nhieu clip trieu view$",
        r"^(?P<channel>.+?) co bao nhieu clip trieu view(?: trong)? (?:thang nay|hom nay|7 ngay qua|30 ngay qua)$",
        r"^(?P<channel>.+?) co bao nhieu clip(?: trong)? (?:thang nay|hom nay|7 ngay qua|30 ngay qua)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, normalized)
        if match:
            return match.group("channel").strip()
    return ""


def resolve_channel_name(question: str, posts: list) -> str | None:
    phrase = extract_channel_phrase(question)
    if not phrase:
        return None
    normalized_phrase = _normalize_text(phrase)
    channel_names = sorted(
        {post.channel_name for post in posts if post.channel_name},
        key=lambda value: len(_normalize_text(value)),
        reverse=True,
    )
    for name in channel_names:
        normalized_name = _normalize_text(name)
        if normalized_name and normalized_name in normalized_phrase:
            return name
    for name in channel_names:
        normalized_name = _normalize_text(name)
        if normalized_phrase and normalized_phrase in normalized_name:
            return name
    return None


def fetch_store_metadata(db_path: Path) -> dict[str, str]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
              MAX(inserted_at) AS last_inserted_at,
              MAX(published_at) AS latest_published_at
            FROM posts
            """
        ).fetchone()
    return {
        "lastInsertedAt": str(row[0] or ""),
        "latestPublishedAt": str(row[1] or ""),
    }


def answer_data_question(db_path: Path, question: str, *, now: datetime | None = None) -> str | None:
    metric = detect_query_metric(question)
    if not metric:
        return None

    posts = load_posts(db_path)
    channel_name = resolve_channel_name(question, posts)
    if not channel_name:
        return (
            "**Khong tim thay kenh trong cau hoi**\n"
            "*Toi chua xac dinh duoc ten kenh tu cau hoi cua ban. Hay ghi ro ten kenh, vi du:* "
            "`Jeeker da dang bao nhieu clip trong thang nay`."
        )

    window = resolve_query_window(question, now=now)
    scoped = [
        post
        for post in posts
        if post.channel_name == channel_name and window.start_date <= post.published_date <= window.end_date
    ]
    metadata = fetch_store_metadata(db_path)

    lines = [
        f"**Tra loi cho kenh {channel_name}**",
        f"*Pham vi phan tich: `{window.start_date.isoformat()} -> {window.end_date.isoformat()}`*",
    ]
    if metric == "clip_count":
        lines.append(f"- So clip da dang: {len(scoped)}")
    elif metric == "million_view_clip_count":
        million_clips = [post for post in scoped if int(post.view) >= 1_000_000]
        lines.append(f"- So clip dat tu 1M view: {len(million_clips)}")
        if million_clips:
            lines.append("- Cac clip dat 1M view:")
            for index, post in enumerate(sorted(million_clips, key=lambda item: item.view, reverse=True)[:5], start=1):
                lines.append(f"  {index}. {compact_number(int(post.view))} view | {post.url}")

    lines.append(f"*Du lieu duoc cap nhat lan cuoi: `{metadata['lastInsertedAt'] or '-'}`*")
    lines.append(f"*Bai viet moi nhat trong kho: `{metadata['latestPublishedAt'] or '-'}`*")
    return "\n".join(lines)

