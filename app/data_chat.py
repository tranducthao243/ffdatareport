from __future__ import annotations

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
    if "so sanh" in normalized or "ai nhieu view hon" in normalized or "ai dang nhieu hon" in normalized:
        return "compare_channels"
    if "top clip" in normalized or "clip top" in normalized:
        return "top_clips"
    if "tong view" in normalized or "bao nhieu view" in normalized:
        if "clip trieu view" not in normalized and "clip 1m" not in normalized and "clip dat 1m" not in normalized:
            return "total_view"
    if "clip trieu view" in normalized or "clip 1m" in normalized or "clip dat 1m" in normalized:
        return "million_view_clip_count"
    if "bao nhieu clip" in normalized or "dang bao nhieu clip" in normalized:
        return "clip_count"
    return None


def resolve_channel_names(question: str, posts: list) -> list[str]:
    normalized_question = _normalize_text(question)
    channel_names = sorted(
        {post.channel_name for post in posts if post.channel_name},
        key=lambda value: len(_normalize_text(value)),
        reverse=True,
    )
    matched: list[tuple[int, str]] = []
    consumed = normalized_question
    for name in channel_names:
        normalized_name = _normalize_text(name)
        if not normalized_name:
            continue
        position = consumed.find(normalized_name)
        if position >= 0:
            matched.append((position, name))
            consumed = consumed.replace(normalized_name, " ")
    matched.sort(key=lambda item: item[0])
    return [name for _, name in matched]


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


def _append_metadata(lines: list[str], metadata: dict[str, str]) -> str:
    lines.append(f"*Du lieu duoc cap nhat lan cuoi: `{metadata['lastInsertedAt'] or '-'}`*")
    lines.append(f"*Bai viet moi nhat trong kho: `{metadata['latestPublishedAt'] or '-'}`*")
    return "\n".join(lines)


def _scope_posts(posts: list, *, channel_name: str, window: QueryWindow) -> list:
    return [
        post
        for post in posts
        if post.channel_name == channel_name and window.start_date <= post.published_date <= window.end_date
    ]


def _answer_single_channel_question(
    *,
    channel_name: str,
    metric: str,
    posts: list,
    window: QueryWindow,
    metadata: dict[str, str],
) -> str:
    scoped = _scope_posts(posts, channel_name=channel_name, window=window)
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
    elif metric == "total_view":
        total_view = sum(int(post.view) for post in scoped)
        lines.append(f"- Tong view: {compact_number(total_view)}")
        lines.append(f"- So clip: {len(scoped)}")
    elif metric == "top_clips":
        ranked = sorted(scoped, key=lambda item: (int(item.view), item.published_at), reverse=True)[:5]
        lines.append(f"- So clip trong cua so nay: {len(scoped)}")
        if ranked:
            lines.append("- Top clip cua kenh:")
            for index, post in enumerate(ranked, start=1):
                lines.append(f"  {index}. {compact_number(int(post.view))} view | {post.url}")
        else:
            lines.append("- Chua co clip nao trong cua so nay.")

    return _append_metadata(lines, metadata)


def _answer_compare_question(
    *,
    channel_names: list[str],
    posts: list,
    window: QueryWindow,
    metadata: dict[str, str],
) -> str:
    left_name, right_name = channel_names[:2]
    left_posts = _scope_posts(posts, channel_name=left_name, window=window)
    right_posts = _scope_posts(posts, channel_name=right_name, window=window)
    left_views = sum(int(post.view) for post in left_posts)
    right_views = sum(int(post.view) for post in right_posts)

    if left_views > right_views:
        verdict = f"{left_name} dang cao hon ve tong view."
    elif right_views > left_views:
        verdict = f"{right_name} dang cao hon ve tong view."
    else:
        verdict = "Hai kenh dang ngang nhau ve tong view."

    lines = [
        f"**So sanh {left_name} va {right_name}**",
        f"*Pham vi phan tich: `{window.start_date.isoformat()} -> {window.end_date.isoformat()}`*",
        f"- {left_name}: {compact_number(left_views)} view | {len(left_posts)} clip",
        f"- {right_name}: {compact_number(right_views)} view | {len(right_posts)} clip",
        f"- Ket luan: {verdict}",
    ]
    return _append_metadata(lines, metadata)


def answer_data_question(db_path: Path, question: str, *, now: datetime | None = None) -> str | None:
    metric = detect_query_metric(question)
    if not metric:
        return None

    posts = load_posts(db_path)
    metadata = fetch_store_metadata(db_path)
    window = resolve_query_window(question, now=now)
    channel_names = resolve_channel_names(question, posts)

    if metric == "compare_channels":
        if len(channel_names) < 2:
            return (
                "**Chua xac dinh du hai kenh de so sanh**\n"
                "*Hay hoi theo dang, vi du:* `So sanh Jeeker va Bac Gau trong thang nay`."
            )
        return _answer_compare_question(
            channel_names=channel_names,
            posts=posts,
            window=window,
            metadata=metadata,
        )

    if not channel_names:
        return (
            "**Khong tim thay kenh trong cau hoi**\n"
            "*Toi chua xac dinh duoc ten kenh tu cau hoi cua ban. Hay ghi ro ten kenh, vi du:* "
            "`Jeeker thang nay da dang bao nhieu clip`."
        )

    return _answer_single_channel_question(
        channel_name=channel_names[0],
        metric=metric,
        posts=posts,
        window=window,
        metadata=metadata,
    )
