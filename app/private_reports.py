from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from analyze.common import StorePost, load_posts

from .health import compact_number, extract_hashtag_query, normalize_command_text


def _recent_window(days: int, *, now: datetime | None = None) -> tuple[date, date]:
    anchor = (now or datetime.now()).date()
    return anchor - timedelta(days=days - 1), anchor


def _load_kol_mapping(mapping_path: Path) -> list[dict[str, Any]]:
    if not mapping_path.exists():
        return []
    payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        items = payload.get("kols") or []
        return items if isinstance(items, list) else []
    return payload if isinstance(payload, list) else []


def _extract_kol_query(text: str) -> str:
    normalized = normalize_command_text(text)
    if not normalized.startswith("kol"):
        return ""
    return normalized[3:].strip()


def _find_kol_entry(entries: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    normalized_query = normalize_command_text(query)
    if not normalized_query:
        return None
    for entry in entries:
        candidates = [normalize_command_text(str(entry.get("name") or ""))]
        candidates.extend(normalize_command_text(str(item)) for item in (entry.get("aliases") or []))
        if normalized_query in {item for item in candidates if item}:
            return entry
    return None


def _post_matches_channel(post: StorePost, channel: dict[str, Any]) -> bool:
    channel_platform = str(channel.get("platform") or "").strip().lower()
    if channel_platform and post.platform != channel_platform:
        return False
    channel_id = str(channel.get("channelId") or "").strip().lower()
    channel_name = str(channel.get("channelName") or "").strip().lower()
    if channel_id and post.channel_id.strip().lower() == channel_id:
        return True
    if channel_name and post.channel_name.strip().lower() == channel_name:
        return True
    return not channel_id and not channel_name


def _filter_posts_by_kol(posts: list[StorePost], channels: list[dict[str, Any]], *, start_date: date, end_date: date) -> list[StorePost]:
    results: list[StorePost] = []
    for post in posts:
        if post.published_date < start_date or post.published_date > end_date:
            continue
        if any(_post_matches_channel(post, channel) for channel in channels):
            results.append(post)
    return results


def _format_top_posts(posts: list[StorePost], *, limit: int) -> list[str]:
    ranked = sorted(posts, key=lambda item: (item.view, item.engagement, item.published_at), reverse=True)[:limit]
    if not ranked:
        return ["- Chua co du lieu."]
    return [f"{index}. {post.url} - {compact_number(post.view)}" for index, post in enumerate(ranked, start=1)]


def _format_top_hashtags(posts: list[StorePost], *, limit: int) -> list[str]:
    counter = Counter(
        tag
        for post in posts
        for tag in post.hashtags
        if str(tag or "").strip()
    )
    if not counter:
        return ["- Chua co du lieu."]
    lines: list[str] = []
    for tag, count in counter.most_common(limit):
        normalized = str(tag).strip()
        if not normalized.startswith("#"):
            normalized = f"#{normalized}"
        lines.append(f"{normalized} - {count}")
    return lines


def _group_channels_by_platform(channels: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {"youtube": [], "tiktok": [], "facebook": []}
    for channel in channels:
        platform = str(channel.get("platform") or "").strip().lower()
        label = str(channel.get("channelName") or channel.get("channelId") or "").strip()
        if not platform or not label:
            continue
        grouped.setdefault(platform, [])
        if label not in grouped[platform]:
            grouped[platform].append(label)
    return grouped


def format_kol_report(db_path: Path, text: str, *, mapping_path: Path, now: datetime | None = None) -> str:
    query = _extract_kol_query(text)
    if not query:
        return (
            "KOL: -\n\n"
            "Vui long dung cu phap: `kol <ten_kol>`."
        )

    mapping = _load_kol_mapping(mapping_path)
    entry = _find_kol_entry(mapping, query)
    if not entry:
        return (
            f"KOL: {query}\n\n"
            "Khong tim thay cau hinh KOL trong he thong."
        )

    start_date, end_date = _recent_window(30, now=now)
    posts = load_posts(db_path)
    channels = list(entry.get("channels") or [])
    scoped = _filter_posts_by_kol(posts, channels, start_date=start_date, end_date=end_date)
    grouped_channels = _group_channels_by_platform(channels)
    top_hashtags = _format_top_hashtags(scoped, limit=3)
    top_posts = _format_top_posts(scoped, limit=3)
    total_views = sum(post.view for post in scoped)

    lines = [
        f"KOL: {entry.get('name', query)}",
        "",
        "Tong quan (30 ngay):",
        f"- Tong view: {compact_number(total_views)}",
        f"- Tong so clip: {len(scoped)}",
        "",
        "TOP 3 video:",
        *top_posts,
        "",
        "TOP hashtag:",
        *top_hashtags,
        "",
        "Kenh:",
        f"- YouTube: {', '.join(grouped_channels.get('youtube') or ['-'])}",
        f"- TikTok: {', '.join(grouped_channels.get('tiktok') or ['-'])}",
        f"- Facebook: {', '.join(grouped_channels.get('facebook') or ['-'])}",
    ]
    return "\n".join(lines)


def format_hashtag_report_v2(db_path: Path, text: str, *, now: datetime | None = None) -> str:
    query = extract_hashtag_query(text)
    if not query:
        return (
            "Hashtag: -\n"
            "Vui long dung cu phap: `hashtag ob53` hoac `hashtagob53`."
        )

    posts = load_posts(db_path)
    matched = [post for post in posts if query in {tag.lstrip('#').lower() for tag in post.hashtags}]
    if not matched:
        return f"Hashtag: #{query}\nKhong tim thay du lieu."

    total_views = sum(post.view for post in matched)
    min_date = min(post.published_date for post in matched).isoformat()
    max_date = max(post.published_date for post in matched).isoformat()
    start_7d, end_7d = _recent_window(7, now=now)
    start_30d, end_30d = _recent_window(30, now=now)
    top_7d = [post for post in matched if start_7d <= post.published_date <= end_7d]
    top_30d = [post for post in matched if start_30d <= post.published_date <= end_30d]
    official_posts = [post for post in matched if post.is_official]
    official_views = sum(post.view for post in official_posts)
    official_count = len(official_posts)
    official_share = round((official_views / total_views) * 100, 2) if total_views else 0.0

    lines = [
        f"Hashtag: #{query}",
        f"Date range: {min_date} -> {max_date}",
        f"Total views: {compact_number(total_views)}",
        f"Total content: {len(matched)}",
        "",
        "TOP VIDEO NOI BAT (7 NGAY)",
        *_format_top_posts(top_7d, limit=5),
        "",
        "TOP VIDEO NOI BAT (30 NGAY)",
        *_format_top_posts(top_30d, limit=5),
        "",
        "Official contribution:",
        f"- Total views: {compact_number(official_views)}",
        f"- Total content: {official_count}",
        f"- Percentage: {official_share}%",
    ]
    return "\n".join(lines)
