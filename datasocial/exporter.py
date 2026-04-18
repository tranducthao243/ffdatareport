from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from .analysis import coerce_int
from .report_engine import build_modular_export_report


DEFAULT_EXPORT_METRIC_IDS = [2, 61, 0, 1, 4]
DEFAULT_EXPORT_TTL = "PT10M"
DEFAULT_EXPORT_METRIC_DURATION = 30


def build_export_filter(
    *,
    created_at_gte: str | None,
    created_at_lte: str | None,
    category_ids: list[int] | None,
    platform_ids: list[int] | None,
    channel_ids: list[int] | None,
    metric_ids: list[int] | None,
    metric_duration: int,
) -> dict[str, Any]:
    export_filter: dict[str, Any] = {}
    if created_at_gte:
        export_filter["createdAt_gte"] = created_at_gte
    if created_at_lte:
        export_filter["createdAt_lte"] = created_at_lte
    if metric_ids:
        export_filter["metricId_in"] = metric_ids
    export_filter["metricDuration"] = metric_duration

    channel_filter: dict[str, Any] = {}
    if category_ids:
        channel_filter["categoryId_in"] = category_ids
    if platform_ids:
        channel_filter["plat_in"] = platform_ids
    if channel_ids:
        channel_filter["id_in"] = channel_ids
    if channel_filter:
        export_filter["channel"] = channel_filter
    return export_filter


def parse_export_csv(csv_bytes: bytes) -> list[dict[str, str]]:
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def export_rows_to_csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def build_export_report(
    rows: list[dict[str, str]],
    *,
    hashtag_filters: list[str] | None,
    event_hashtags: list[str] | None,
    report_mode: str,
    timezone_name: str,
    fetch_window_label: str,
    top_limit: int,
    trend_min_views: int = 200_000,
    now: datetime | None = None,
) -> dict[str, Any]:
    return build_modular_export_report(
        rows,
        hashtag_filters=hashtag_filters,
        event_hashtags=event_hashtags,
        mode=report_mode,
        timezone_name=timezone_name,
        fetch_window_label=fetch_window_label,
        now=now,
        top_limit=top_limit,
        trend_min_views=trend_min_views,
    )


def filter_export_rows(
    rows: list[dict[str, str]],
    *,
    category_names: list[str] | None,
    hashtag_filters: list[str] | None,
) -> list[dict[str, str]]:
    category_set = set(category_names or [])
    hashtag_terms = [item.lower() for item in (hashtag_filters or [])]
    results = []
    for row in rows:
        if category_set and (row.get("Category") or "") not in category_set:
            continue
        if hashtag_terms:
            hashtag_text = (row.get("Hashtag") or "").lower()
            if not any(term in hashtag_text for term in hashtag_terms):
                continue
        results.append(row)
    return results


def filter_by_hashtags(rows: list[dict[str, str]], hashtags: list[str]) -> list[dict[str, str]]:
    terms = [item.lower() for item in hashtags]
    if not terms:
        return []
    return [
        row for row in rows if any(term in (row.get("Hashtag") or "").lower() for term in terms)
    ]


def rows_in_last_days(rows: list[dict[str, str]], days: int, now: datetime) -> list[dict[str, str]]:
    cutoff = now - timedelta(days=days)
    results = []
    for row in rows:
        published_at = parse_publish_time(row.get("Publish time") or "")
        if published_at and published_at >= cutoff:
            results.append(row)
    return results


def sort_rows_by_view(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: coerce_int(row.get("View")) or 0, reverse=True)


def summarize_export_low_activity(
    rows: list[dict[str, str]],
    *,
    threshold: int,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (
            row.get("Channel id") or "",
            row.get("Channel name") or "",
            row.get("Category") or "",
        )
        buckets[key].append(row)

    results: list[dict[str, Any]] = []
    for (channel_id, channel_name, category), items in buckets.items():
        if len(items) > threshold:
            continue
        latest_row = max(
            items,
            key=lambda row: parse_publish_time(row.get("Publish time") or "") or datetime.min,
        )
        results.append(
            {
                "channelId": channel_id,
                "channelName": channel_name,
                "category": category,
                "postCount30Days": len(items),
                "lastPublishedAt": latest_row.get("Publish time") or "",
                "topView30Days": max(coerce_int(item.get("View")) or 0 for item in items),
            }
        )
    return sorted(results, key=lambda item: (item["postCount30Days"], item["topView30Days"]))


def serialize_export_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "title": row.get("Post description") or "",
            "url": row.get("Link") or "",
            "createdAt": row.get("Publish time") or "",
            "view": coerce_int(row.get("View")) or 0,
            "channelId": row.get("Channel id") or "",
            "channelName": row.get("Channel name") or "",
            "category": row.get("Category") or "",
            "hashtags": split_hashtags(row.get("Hashtag") or ""),
            "postId": row.get("Post id") or "",
            "platform": row.get("Platform") or "",
            "engagement": coerce_int(row.get("Engagement")) or 0,
        }
        for row in rows
    ]


def split_hashtags(text: str) -> list[str]:
    return [token for token in text.split() if token.startswith("#")]


def parse_publish_time(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def build_daily_windows(start_date: str, end_date: str) -> list[tuple[str, str]]:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    windows: list[tuple[str, str]] = []
    current = start
    while current <= end:
        iso = current.isoformat()
        windows.append((iso, iso))
        current += timedelta(days=1)
    return windows


def dedupe_export_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, str]] = []
    for row in rows:
        key = (
            row.get("Post id") or "",
            row.get("Link") or "",
            row.get("Channel id") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped
