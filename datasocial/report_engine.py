from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any

from .models import ExportRecord
from .normalize import filter_records_by_hashtags, normalize_export_rows
from .timewindows import DEFAULT_REPORT_TZ, DateWindow, build_date_window, get_report_timezone


PLATFORM_ORDER = ("tiktok", "youtube")
TOP_CONTENT_WINDOWS = ("1D",)
ANALYTICS_WINDOW = "7D"
MAX_FETCH_WINDOW = "30D"


def build_reporting_context(
    *,
    mode: str,
    timezone_name: str = DEFAULT_REPORT_TZ,
    fetch_window_label: str = MAX_FETCH_WINDOW,
    now: datetime | None = None,
) -> dict[str, Any]:
    tz = get_report_timezone(timezone_name)
    fetch_window = build_date_window(
        fetch_window_label,
        mode=mode,
        timezone_name=timezone_name,
        now=now,
    )
    return {
        "mode": mode,
        "timezone": timezone_name,
        "generatedAt": (now or datetime.now(tz)).astimezone(tz),
        "fetchWindow": fetch_window,
        "sectionWindows": {
            label: build_date_window(label, mode=mode, timezone_name=timezone_name, now=now)
            for label in ("1D", "4D", "7D", "30D")
        },
    }


def build_modular_export_report(
    rows: list[dict[str, str]],
    *,
    hashtag_filters: list[str] | None,
    event_hashtags: list[str] | None,
    mode: str,
    timezone_name: str = DEFAULT_REPORT_TZ,
    fetch_window_label: str = "7D",
    now: datetime | None = None,
    top_limit: int = 5,
    trend_min_views: int = 200_000,
) -> dict[str, Any]:
    context = build_reporting_context(
        mode=mode,
        timezone_name=timezone_name,
        fetch_window_label=fetch_window_label,
        now=now,
    )
    records = normalize_export_rows(rows, timezone_name=timezone_name)
    filtered_records = filter_records_by_hashtags(records, hashtag_filters)
    analytics_window = context["sectionWindows"][ANALYTICS_WINDOW]
    overview_records_7d = filter_records_by_window(records, analytics_window)

    report = {
        "generatedAt": context["generatedAt"].isoformat(),
        "meta": {
            "timezone": timezone_name,
            "windowMode": mode,
            "supportedWindows": ["1D", "4D", "7D", "30D"],
            "fetchWindow": asdict(context["fetchWindow"]),
            "sectionWindows": {
                key: asdict(window) for key, window in context["sectionWindows"].items()
            },
        },
        "summary": {
            "rowsFetched": len(records),
            "rowsAfterFilters": len(filtered_records),
            "platformCounts": summarize_platform_counts(filtered_records),
            "campaignTracking": "planned",
        },
        "modules": {
            "topContentByPlatform": {
                label: build_top_content_by_platform(
                    filtered_records,
                    window=context["sectionWindows"][label],
                    top_limit=top_limit,
                )
                for label in TOP_CONTENT_WINDOWS
            },
            "trendVideos7D": build_trend_videos(
                filtered_records,
                window=analytics_window,
                top_limit=top_limit,
                min_views=trend_min_views,
            ),
            "dailyViews7D": build_daily_view_series(overview_records_7d, analytics_window),
            "dailyPostCount7D": build_daily_post_series(filtered_records, analytics_window),
            "topKols7D": build_top_kols(filtered_records, analytics_window, top_limit=top_limit),
            "overview7D": build_overview_summary(overview_records_7d),
            "campaignTracking": {
                "status": "future",
                "note": "Campaign KPI, pacing, and cross-campaign comparison will be added after the GitHub workflow and UI are in place.",
                "eventHashtagsConfigured": event_hashtags or [],
            },
        },
    }
    return report


def summarize_platform_counts(records: list[ExportRecord]) -> dict[str, int]:
    counts: dict[str, int] = {platform: 0 for platform in PLATFORM_ORDER}
    for record in records:
        counts[record.platform_key] = counts.get(record.platform_key, 0) + 1
    return counts


def build_top_content_by_platform(
    records: list[ExportRecord],
    *,
    window: DateWindow,
    top_limit: int,
) -> dict[str, list[dict[str, Any]]]:
    scoped = filter_records_by_window(records, window)
    result: dict[str, list[dict[str, Any]]] = {}
    for platform in PLATFORM_ORDER:
        platform_records = [record for record in scoped if record.platform_key == platform]
        ranked = sorted(platform_records, key=lambda record: record.view, reverse=True)[:top_limit]
        result[platform] = [serialize_content_record(record) for record in ranked]
    return result


def build_trend_videos(
    records: list[ExportRecord],
    *,
    window: DateWindow,
    top_limit: int,
    min_views: int,
) -> list[dict[str, Any]]:
    scoped = filter_records_by_window(records, window)
    channel_buckets: dict[str, list[ExportRecord]] = defaultdict(list)
    for record in scoped:
        channel_buckets[record.channel_id].append(record)

    trend_rows: list[dict[str, Any]] = []
    for channel_records in channel_buckets.values():
        if len(channel_records) < 3:
            continue
        for record in channel_records:
            if record.view < min_views:
                continue
            peers = [item.view for item in channel_records if item.post_id != record.post_id and item.view > 0]
            if not peers:
                continue
            baseline_view = int(median(peers))
            if baseline_view <= 0:
                continue
            ratio = record.view / baseline_view
            trend_rows.append(
                {
                    **serialize_content_record(record),
                    "baselineView": baseline_view,
                    "trendRatio": round(ratio, 2),
                    "trendLift": record.view - baseline_view,
                }
            )
    return sorted(
        trend_rows,
        key=lambda item: (item["trendRatio"], item["view"]),
        reverse=True,
    )[:top_limit]


def build_daily_view_series(records: list[ExportRecord], window: DateWindow) -> dict[str, Any]:
    scoped = filter_records_by_window(records, window)
    totals = aggregate_daily(scoped, field="view", window=window)
    peak_day = max(totals, key=lambda item: item["value"], default=None)
    low_day = min(totals, key=lambda item: item["value"], default=None)
    peak_hour_range, peak_hour_count = build_peak_posting_hour_from_top_views(scoped, limit=100)
    return {
        "peakDate": peak_day["date"] if peak_day else "",
        "peakValue": peak_day["value"] if peak_day else 0,
        "lowDate": low_day["date"] if low_day else "",
        "lowValue": low_day["value"] if low_day else 0,
        "peakPostingHourRange": peak_hour_range,
        "peakPostingHourCount": peak_hour_count,
    }


def build_daily_post_series(records: list[ExportRecord], window: DateWindow) -> dict[str, Any]:
    scoped = filter_records_by_window(records, window)
    totals = aggregate_daily(scoped, field="count", window=window)
    peak_day = max(totals, key=lambda item: item["value"], default=None)
    low_day = min(totals, key=lambda item: item["value"], default=None)
    return {
        "peakDate": peak_day["date"] if peak_day else "",
        "peakValue": peak_day["value"] if peak_day else 0,
        "lowDate": low_day["date"] if low_day else "",
        "lowValue": low_day["value"] if low_day else 0,
    }


def build_top_kols(
    records: list[ExportRecord],
    window: DateWindow,
    *,
    top_limit: int,
) -> dict[str, list[dict[str, Any]]]:
    scoped = filter_records_by_window(records, window)
    result: dict[str, list[dict[str, Any]]] = {}
    for platform in PLATFORM_ORDER:
        buckets: dict[str, dict[str, Any]] = {}
        for record in scoped:
            if record.platform_key != platform:
                continue
            key = record.channel_id or record.channel_name
            entry = buckets.setdefault(
                key,
                {
                    "channelId": record.channel_id,
                    "channelName": record.channel_name,
                    "platform": platform,
                    "totalView": 0,
                    "postCount": 0,
                },
            )
            entry["totalView"] += record.view
            entry["postCount"] += 1
        result[platform] = sorted(
            buckets.values(),
            key=lambda item: (item["totalView"], item["postCount"]),
            reverse=True,
        )[:top_limit]
    return result


def build_overview_summary(records: list[ExportRecord]) -> dict[str, Any]:
    total_view = sum(record.view for record in records)
    total_posts = len(records)
    return {
        "totalView": total_view,
        "totalPosts": total_posts,
        "averageView": int(total_view / total_posts) if total_posts else 0,
        "dateRange": {
            "from": min((record.published_at.date().isoformat() for record in records), default=""),
            "to": max((record.published_at.date().isoformat() for record in records), default=""),
        },
    }


def build_peak_posting_hour_from_top_views(records: list[ExportRecord], *, limit: int) -> tuple[str, int]:
    if not records:
        return "", 0
    top_records = sorted(records, key=lambda record: record.view, reverse=True)[:limit]
    counts: dict[int, int] = defaultdict(int)
    for record in top_records:
        counts[record.published_at.hour] += 1
    peak_hour, count = max(counts.items(), key=lambda item: (item[1], -item[0]))
    return f"{peak_hour:02d}:00-{(peak_hour + 1) % 24:02d}:00", count


def filter_records_by_window(records: list[ExportRecord], window: DateWindow) -> list[ExportRecord]:
    start = date.fromisoformat(window.start_date)
    end = date.fromisoformat(window.end_date)
    return [
        record
        for record in records
        if start <= record.published_at.date() <= end
    ]


def aggregate_daily(
    records: list[ExportRecord],
    *,
    field: str,
    window: DateWindow,
) -> list[dict[str, Any]]:
    totals = build_zero_series(window)
    for record in records:
        bucket = record.published_at.date().isoformat()
        if field == "count":
            totals[bucket] += 1
        else:
            totals[bucket] += record.view
    return [{"date": key, "value": value} for key, value in totals.items()]


def build_zero_series(window: DateWindow) -> dict[str, int]:
    start = date.fromisoformat(window.start_date)
    end = date.fromisoformat(window.end_date)
    values: dict[str, int] = {}
    current = start
    while current <= end:
        values[current.isoformat()] = 0
        current += timedelta(days=1)
    return values


def serialize_content_record(record: ExportRecord) -> dict[str, Any]:
    return {
        "title": clean_title(record.description),
        "url": record.url,
        "platform": record.platform_key,
        "channelId": record.channel_id,
        "channelName": record.channel_name,
        "postId": record.post_id,
        "postType": record.post_type,
        "category": record.category,
        "view": record.view,
        "engagement": record.engagement,
        "comment": record.comment,
        "reaction": record.reaction,
        "durationSeconds": record.duration_seconds,
        "hashtags": record.hashtags,
        "publishedAt": record.published_at.isoformat(),
    }


def clean_title(value: str) -> str:
    first_line = next((line.strip() for line in value.splitlines() if line.strip()), "")
    compact = " ".join(first_line.split())
    if len(compact) <= 140:
        return compact
    return compact[:139] + "…"
