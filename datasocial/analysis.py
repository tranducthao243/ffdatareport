from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import PostRecord


def build_report(
    posts: list[PostRecord],
    *,
    hashtag_filters: list[str] | None = None,
    low_activity_threshold: int = 4,
    top_limit: int = 10,
    event_hashtags: list[str] | None = None,
) -> dict[str, Any]:
    normalized_posts = [enrich_post(post) for post in posts]
    hashtag_filters = [item.lower() for item in (hashtag_filters or [])]
    if hashtag_filters:
        normalized_posts = [
            post for post in normalized_posts if matches_any_hashtag(post, hashtag_filters)
        ]

    weekly_posts = posts_in_last_days(normalized_posts, 7)
    recent_posts = posts_in_last_days(normalized_posts, 3)
    last_month_posts = posts_in_last_days(normalized_posts, 30)
    event_tags = [item.lower() for item in (event_hashtags or hashtag_filters or [])]
    highlight_posts = [
        post for post in weekly_posts if event_tags and matches_any_hashtag(post, event_tags)
    ]

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "totalPostsFetched": len(posts),
            "totalPostsAfterHashtagFilter": len(normalized_posts),
            "weeklyPosts": len(weekly_posts),
            "recent3DayPosts": len(recent_posts),
            "eventHighlightPosts": len(highlight_posts),
        },
        "weeklyTopVideos": serialize_posts(sort_posts_by_view(weekly_posts)[:top_limit]),
        "topVideos3Days": serialize_posts(sort_posts_by_view(recent_posts)[:top_limit]),
        "eventHighlights7Days": serialize_posts(sort_posts_by_view(highlight_posts)[:top_limit]),
        "lowActivityChannels30Days": summarize_low_activity_channels(
            last_month_posts,
            threshold=low_activity_threshold,
        )[:top_limit],
        "notes": [
            "Low-activity channels are derived from channels observed in fetched posts.",
            "To detect completely inactive channels, the tool needs a full channel roster query.",
        ],
    }


def enrich_post(post: PostRecord) -> PostRecord:
    post.metrics.setdefault("view", extract_view(post))
    post.metrics.setdefault("channel_id", extract_channel_id(post))
    post.metrics.setdefault("channel_name", extract_channel_name(post))
    post.metrics.setdefault("hashtags", extract_hashtags(post))
    return post


def extract_view(post: PostRecord) -> int:
    metrics = post.metrics or {}
    candidate_keys = (
        "view",
        "views",
        "organic_view",
        "organicView",
        "impression",
        "reach",
    )
    for key in candidate_keys:
        value = metrics.get(key)
        parsed = coerce_int(value)
        if parsed is not None:
            return parsed
    return 0


def extract_channel_id(post: PostRecord) -> str:
    raw = post.raw
    return str(raw.get("channelId") or raw.get("channel_id") or "")


def extract_channel_name(post: PostRecord) -> str:
    raw = post.raw
    return str(raw.get("alias") or raw.get("channelName") or "")


def extract_hashtags(post: PostRecord) -> list[str]:
    raw_text = " ".join(
        str(part or "")
        for part in [post.raw.get("tags"), post.raw.get("sub"), post.title]
    ).lower()
    return [token for token in raw_text.split() if token.startswith("#")]


def matches_any_hashtag(post: PostRecord, hashtags: list[str]) -> bool:
    post_hashtags = {tag.lower() for tag in extract_hashtags(post)}
    return any(tag.lower() in post_hashtags for tag in hashtags)


def posts_in_last_days(posts: list[PostRecord], days: int) -> list[PostRecord]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    results: list[PostRecord] = []
    for post in posts:
        created_at = parse_created_at(post.created_at)
        if created_at and created_at >= cutoff:
            results.append(post)
    return results


def sort_posts_by_view(posts: list[PostRecord]) -> list[PostRecord]:
    return sorted(posts, key=extract_view, reverse=True)


def summarize_low_activity_channels(
    posts: list[PostRecord],
    *,
    threshold: int,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[PostRecord]] = defaultdict(list)
    for post in posts:
        channel_id = extract_channel_id(post)
        channel_name = extract_channel_name(post)
        buckets[(channel_id, channel_name)].append(post)

    results: list[dict[str, Any]] = []
    for (channel_id, channel_name), items in buckets.items():
        if len(items) > threshold:
            continue
        last_post = max(
            items,
            key=lambda item: parse_created_at(item.created_at)
            or datetime.min.replace(tzinfo=timezone.utc),
        )
        results.append(
            {
                "channelId": channel_id,
                "channelName": channel_name,
                "postCount30Days": len(items),
                "lastPublishedAt": last_post.created_at,
                "topView30Days": max(extract_view(item) for item in items) if items else 0,
            }
        )
    return sorted(results, key=lambda item: (item["postCount30Days"], item["topView30Days"]))


def serialize_posts(posts: list[PostRecord]) -> list[dict[str, Any]]:
    return [
        {
            "title": post.title,
            "url": post.url,
            "createdAt": post.created_at,
            "view": extract_view(post),
            "channelId": extract_channel_id(post),
            "channelName": extract_channel_name(post),
            "hashtags": extract_hashtags(post),
            "metrics": post.metrics,
        }
        for post in posts
    ]


def parse_created_at(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.replace(",", "")))
        except ValueError:
            return None
    return None
