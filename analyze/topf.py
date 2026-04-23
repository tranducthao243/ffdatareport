from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .common import OFFICIAL_PLATFORMS, build_anchor_window, build_days_window, filter_posts, load_posts, rank_posts, serialize_post


VIDEO_LIKE_TYPES = {"video", "reel", "live"}
PHOTO_ENGAGEMENT_TYPES = {"text", "photo", "link", "album"}


def analyze_topf(
    db_path: Path,
    *,
    mode: str = "complete_previous_day",
    timezone_name: str,
    now: datetime | None = None,
    limit: int = 5,
) -> dict:
    posts = load_posts(db_path)
    top_start, top_end = build_days_window(3, mode=mode, timezone_name=timezone_name, now=now)
    seven_start, seven_end = build_anchor_window("7D", mode=mode, timezone_name=timezone_name, now=now)
    top_posts = filter_posts(
        posts,
        start_date=top_start,
        end_date=top_end,
        platforms=OFFICIAL_PLATFORMS,
        require_official=True,
    )
    top_video_posts = [
        post for post in top_posts
        if str(getattr(post, "post_type", "") or "").strip().lower() in VIDEO_LIKE_TYPES
    ]
    top_photo_posts = [
        post for post in top_posts
        if str(getattr(post, "post_type", "") or "").strip().lower() in PHOTO_ENGAGEMENT_TYPES
    ]
    top_photo_ranked = sorted(
        top_photo_posts,
        key=lambda post: (post.reaction, post.engagement, post.published_at),
        reverse=True,
    )[:3]
    fanpage_posts_3d = [
        post
        for post in top_posts
        if post.platform == "facebook"
    ]
    weekly_posts = filter_posts(
        posts,
        start_date=seven_start,
        end_date=seven_end,
        platforms=OFFICIAL_PLATFORMS,
        require_official=True,
    )
    weekly_video_posts = [
        post for post in weekly_posts
        if str(getattr(post, "post_type", "") or "").strip().lower() in VIDEO_LIKE_TYPES
    ]
    totals_by_platform: dict[str, dict[str, int]] = {}
    for platform in OFFICIAL_PLATFORMS:
        scoped = [post for post in weekly_video_posts if post.platform == platform]
        totals_by_platform[platform] = {
            "totalViews": sum(post.view for post in scoped),
            "totalClips": len(scoped),
        }
    today = (now or datetime.now()).date()
    chart_start = today - timedelta(days=29)
    chart_posts = [
        post
        for post in filter_posts(
            posts,
            start_date=chart_start,
            end_date=today,
            platforms=OFFICIAL_PLATFORMS,
            require_official=True,
        )
        if str(getattr(post, "post_type", "") or "").strip().lower() in VIDEO_LIKE_TYPES
    ]
    chart_daily: list[dict[str, object]] = []
    peak_day_channels: dict[tuple[str, str, str], dict[str, object]] = {}
    peak_day_total = -1
    peak_day_iso = ""
    for offset in range(30):
        day = chart_start + timedelta(days=offset)
        day_posts = [post for post in chart_posts if post.published_date == day]
        day_total = sum(post.view for post in day_posts)
        chart_daily.append({"date": day.isoformat(), "totalViews": day_total})
        if day_total > peak_day_total:
            peak_day_total = day_total
            peak_day_iso = day.isoformat()
            peak_day_channels = {}
            for post in day_posts:
                key = (post.platform, post.channel_id, post.channel_name)
                entry = peak_day_channels.setdefault(
                    key,
                    {"platform": post.platform, "channelName": post.channel_name, "totalViews": 0},
                )
                entry["totalViews"] = int(entry["totalViews"]) + post.view
    peak_day_top_channels = [
        {
            "platform": str(item["platform"]),
            "channelName": str(item["channelName"]),
            "totalViews": int(item["totalViews"]),
        }
        for item in sorted(
            peak_day_channels.values(),
            key=lambda item: (int(item["totalViews"]), str(item["channelName"])),
            reverse=True,
        )[:3]
    ]
    return {
        "code": "TOPF",
        "title": "TOPF",
        "topWindow": {"from": top_start.isoformat(), "to": top_end.isoformat()},
        "summaryWindow": {"from": seven_start.isoformat(), "to": seven_end.isoformat()},
        "topVideos": rank_posts(top_video_posts, limit=limit),
        "topPhotoEngagement": [serialize_post(post) for post in top_photo_ranked],
        "totalFanpagePosts3D": len(fanpage_posts_3d),
        "platformTotals": totals_by_platform,
        "dailyChart": chart_daily,
        "peakDay": {
            "date": peak_day_iso,
            "totalViews": max(peak_day_total, 0),
            "topChannels": peak_day_top_channels,
        },
    }
