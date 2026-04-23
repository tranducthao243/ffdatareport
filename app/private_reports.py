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
    collapsed_query = normalized_query.replace(" ", "")
    query_tokens = [token for token in normalized_query.split() if token]
    for entry in entries:
        candidates = [normalize_command_text(str(entry.get("name") or ""))]
        candidates.extend(normalize_command_text(str(item)) for item in (entry.get("aliases") or []))
        for candidate in {item for item in candidates if item}:
            collapsed_candidate = candidate.replace(" ", "")
            candidate_tokens = candidate.split()
            if (
                normalized_query == candidate
                or collapsed_query == collapsed_candidate
                or normalized_query in candidate
                or candidate in normalized_query
                or all(token in candidate_tokens or token in candidate for token in query_tokens)
            ):
                return entry
    return None


def _post_matches_channel(post: StorePost, channel: dict[str, Any]) -> bool:
    channel_platform = str(channel.get("platform") or "").strip().lower()
    if channel_platform and post.platform != channel_platform:
        return False
    channel_id = str(channel.get("channelId") or "").strip().lower()
    channel_name = normalize_command_text(str(channel.get("channelName") or "").strip())
    if channel_id and post.channel_id.strip().lower() == channel_id:
        return True
    post_channel_name = normalize_command_text(post.channel_name)
    if channel_name and post_channel_name == channel_name:
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


def _build_fallback_kol_entry(posts: list[StorePost], query: str) -> dict[str, Any] | None:
    normalized_query = normalize_command_text(query)
    collapsed_query = normalized_query.replace(" ", "")
    query_tokens = [token for token in normalized_query.split() if token]
    channels: dict[tuple[str, str, str], dict[str, Any]] = {}
    for post in posts:
        if not post.is_kol:
            continue
        normalized_name = normalize_command_text(post.channel_name)
        collapsed_name = normalized_name.replace(" ", "")
        name_tokens = [token for token in normalized_name.split() if token]
        if not normalized_name:
            continue
        if (
            normalized_query == normalized_name
            or collapsed_query == collapsed_name
            or normalized_query in normalized_name
            or normalized_name in normalized_query
            or all(token in name_tokens or token in normalized_name for token in query_tokens)
        ):
            key = (post.platform, post.channel_id, post.channel_name)
            channels[key] = {
                "platform": post.platform,
                "channelId": post.channel_id,
                "channelName": post.channel_name,
            }
    if not channels:
        return None
    primary_name = sorted(channels.values(), key=lambda item: (item["platform"], item["channelName"]))[0]["channelName"]
    return {
        "name": primary_name,
        "aliases": [query],
        "channels": list(channels.values()),
    }


def _format_top_posts(posts: list[StorePost], *, limit: int) -> list[str]:
    ranked = sorted(posts, key=lambda item: (item.view, item.engagement, item.published_at), reverse=True)[:limit]
    if not ranked:
        return ["- Chưa có dữ liệu."]
    return [
        f"{index}. {post.channel_name} | {post.url} - {compact_number(post.view)}"
        for index, post in enumerate(ranked, start=1)
    ]


def _format_top_posts_by_platform(posts: list[StorePost], *, platform: str, limit: int) -> list[str]:
    scoped = [post for post in posts if post.platform == platform]
    return _format_top_posts(scoped, limit=limit)


def _format_top_hashtags(posts: list[StorePost], *, limit: int) -> list[str]:
    counter = Counter(tag for post in posts for tag in post.hashtags if str(tag or "").strip())
    if not counter:
        return ["- Chưa có dữ liệu."]
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


def _format_channel_summary(posts: list[StorePost], *, limit: int) -> list[str]:
    channel_stats: dict[tuple[str, str, str], dict[str, Any]] = {}
    for post in posts:
        key = (post.platform, post.channel_id, post.channel_name)
        entry = channel_stats.setdefault(
            key,
            {
                "platform": post.platform,
                "channel_name": post.channel_name,
                "total_views": 0,
                "total_clips": 0,
            },
        )
        entry["total_views"] += post.view
        entry["total_clips"] += 1

    ranked = sorted(
        channel_stats.values(),
        key=lambda item: (item["total_views"], item["total_clips"], item["channel_name"]),
        reverse=True,
    )[:limit]
    if not ranked:
        return ["- Chưa có dữ liệu."]
    return [
        f"- {item['channel_name']} ({item['platform'].title()}): {compact_number(item['total_views'])} view | {item['total_clips']} clip"
        for item in ranked
    ]


def format_kol_report(db_path: Path, text: str, *, mapping_path: Path, now: datetime | None = None) -> str:
    query = _extract_kol_query(text)
    if not query:
        return "KOL: -\n\nVui lòng dùng cú pháp: `kol <tên KOL>`."

    posts = load_posts(db_path)
    mapping = _load_kol_mapping(mapping_path)
    entry = _find_kol_entry(mapping, query) or _build_fallback_kol_entry(posts, query)
    if not entry:
        return (
            f"KOL: {query}\n\n"
            "Không tìm thấy cấu hình hoặc tên kênh KOL trong hệ thống.\n"
            "Hãy bổ sung KOL vào `config/kol_channels.json` với `name`, `aliases` và `channels`, "
            "hoặc gõ đúng tên kênh KOL đang có trong data."
        )

    start_date, end_date = _recent_window(30, now=now)
    channels = list(entry.get("channels") or [])
    scoped = _filter_posts_by_kol(posts, channels, start_date=start_date, end_date=end_date)
    grouped_channels = _group_channels_by_platform(channels)
    top_hashtags = _format_top_hashtags(scoped, limit=3)
    top_posts = _format_top_posts(scoped, limit=3)
    total_views = sum(post.view for post in scoped)

    lines = [
        f"KOL: {entry.get('name', query)}",
        "",
        "Tổng quan (30 ngày):",
        f"- Tổng view: {compact_number(total_views)}",
        f"- Tổng số clip: {len(scoped)}",
        "",
        "TOP 3 video:",
        *top_posts,
        "",
        "TOP 3 video TikTok:",
        *_format_top_posts_by_platform(scoped, platform="tiktok", limit=3),
        "",
        "TOP 3 video YouTube:",
        *_format_top_posts_by_platform(scoped, platform="youtube", limit=3),
        "",
        "TOP hashtag:",
        *top_hashtags,
        "",
        "Kênh:",
        f"- YouTube: {', '.join(grouped_channels.get('youtube') or ['-'])}",
        f"- TikTok: {', '.join(grouped_channels.get('tiktok') or ['-'])}",
        f"- Facebook: {', '.join(grouped_channels.get('facebook') or ['-'])}",
    ]
    return "\n".join(lines)


def format_hashtag_report_v2(db_path: Path, text: str, *, now: datetime | None = None) -> str:
    query = extract_hashtag_query(text)
    if not query:
        return "Hashtag: -\nVui lòng dùng cú pháp: `hashtag ob53` hoặc `hashtagob53`."

    posts = load_posts(db_path)
    matched = [post for post in posts if query in {tag.lstrip('#').lower() for tag in post.hashtags}]
    if not matched:
        return f"Hashtag: #{query}\nKhông tìm thấy dữ liệu."

    total_views = sum(post.view for post in matched)
    min_date = min(post.published_date for post in matched).isoformat()
    max_date = max(post.published_date for post in matched).isoformat()
    start_7d, end_7d = _recent_window(7, now=now)
    start_30d, end_30d = _recent_window(30, now=now)
    top_7d = [post for post in matched if start_7d <= post.published_date <= end_7d]
    top_30d = [post for post in matched if start_30d <= post.published_date <= end_30d]
    official_posts = [post for post in matched if post.is_official or post.category_id == 13]
    official_views = sum(post.view for post in official_posts)
    official_count = len(official_posts)
    official_share = round((official_views / total_views) * 100, 2) if total_views else 0.0
    kol_posts = [post for post in matched if post.is_kol]

    lines = [
        f"Hashtag: #{query}",
        f"Date range: {min_date} -> {max_date}",
        f"Total views: {compact_number(total_views)}",
        f"Total content: {len(matched)}",
        "",
        "TOP VIDEO NỔI BẬT (7 NGÀY)",
        *_format_top_posts(top_7d, limit=5),
        "",
        "TOP VIDEO NỔI BẬT (30 NGÀY)",
        *_format_top_posts(top_30d, limit=5),
        "",
        "KÊNH KOLS:",
        *_format_channel_summary(kol_posts, limit=5),
        "",
        "Official contribution:",
        f"- Total views: {compact_number(official_views)}",
        f"- Total content: {official_count}",
        f"- Percentage: {official_share}%",
    ]
    return "\n".join(lines)
