from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_REPORT_TZ = "Asia/Ho_Chi_Minh"
SUPPORTED_WINDOW_DAYS = {"1D": 1, "4D": 4, "7D": 7, "30D": 30}
SUPPORTED_WINDOW_MODES = {"complete_previous_day", "today_so_far"}


@dataclass(slots=True)
class DateWindow:
    label: str
    days: int
    mode: str
    timezone: str
    start_date: str
    end_date: str
    anchor_date: str


def resolve_window_days(label: str) -> int:
    normalized = label.upper()
    if normalized not in SUPPORTED_WINDOW_DAYS:
        raise ValueError(f"Unsupported report window: {label}")
    return SUPPORTED_WINDOW_DAYS[normalized]


def get_report_timezone(timezone_name: str = DEFAULT_REPORT_TZ):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        # Fallback for Windows/Python environments missing IANA tzdata.
        return timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")


def build_date_window(
    label: str,
    *,
    mode: str,
    timezone_name: str = DEFAULT_REPORT_TZ,
    now: datetime | None = None,
) -> DateWindow:
    if mode not in SUPPORTED_WINDOW_MODES:
        raise ValueError(f"Unsupported report mode: {mode}")

    days = resolve_window_days(label)
    tz = get_report_timezone(timezone_name)
    local_now = (now or datetime.now(tz)).astimezone(tz)

    if mode == "complete_previous_day":
        anchor_date = local_now.date() - timedelta(days=1)
    else:
        anchor_date = local_now.date()

    start_date = anchor_date - timedelta(days=days - 1)
    return DateWindow(
        label=label.upper(),
        days=days,
        mode=mode,
        timezone=timezone_name,
        start_date=start_date.isoformat(),
        end_date=anchor_date.isoformat(),
        anchor_date=anchor_date.isoformat(),
    )
