from __future__ import annotations

from datetime import datetime
from typing import Any

from .analysis import coerce_int
from .models import ExportRecord
from .timewindows import DEFAULT_REPORT_TZ, get_report_timezone


def normalize_export_rows(
    rows: list[dict[str, str]],
    *,
    timezone_name: str = DEFAULT_REPORT_TZ,
) -> list[ExportRecord]:
    timezone = get_report_timezone(timezone_name)
    normalized: list[ExportRecord] = []
    for row in rows:
        published_at = parse_publish_time(row.get("Publish time") or "", timezone)
        if not published_at:
            continue
        normalized.append(
            ExportRecord(
                row_id=str(row.get("ID") or ""),
                platform=row.get("Platform") or "",
                platform_key=normalize_platform(row.get("Platform") or ""),
                channel_id=str(row.get("Channel id") or ""),
                channel_name=(row.get("Channel name") or "").strip(),
                category=(row.get("Category") or "").strip(),
                post_id=str(row.get("Post id") or ""),
                post_type=(row.get("Post type") or "").strip(),
                description=(row.get("Post description") or "").strip(),
                url=(row.get("Link") or "").strip(),
                published_at=published_at,
                hashtags=split_hashtags(row.get("Hashtag") or ""),
                comment=coerce_int(row.get("Comment")) or 0,
                duration_seconds=coerce_int(row.get("Duration (second)")) or 0,
                engagement=coerce_int(row.get("Engagement")) or 0,
                reaction=coerce_int(row.get("Reaction")) or 0,
                view=coerce_int(row.get("View")) or 0,
                raw=row,
            )
        )
    return normalized


def parse_publish_time(value: str, timezone) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone)
    except ValueError:
        return None


def normalize_platform(value: str) -> str:
    text = value.strip().lower()
    if text == "youtube":
        return "youtube"
    if text == "tiktok":
        return "tiktok"
    return text


def split_hashtags(text: str) -> list[str]:
    tokens = [token.strip() for token in text.replace("\n", " ").split() if token.strip()]
    results: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if not token.startswith("#"):
            continue
        normalized = token.rstrip(",.;:!?)(")
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(normalized)
    return results


def filter_records_by_hashtags(
    records: list[ExportRecord],
    hashtags: list[str] | None,
) -> list[ExportRecord]:
    if not hashtags:
        return records
    terms = {item.lower() for item in hashtags}
    return [
        record
        for record in records
        if any(tag.lower() in terms for tag in record.hashtags)
    ]
