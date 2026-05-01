from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from analyze.common import KOL_CATEGORY_IDS, KOL_PLATFORMS, ROBLOX_CATEGORY_IDS, filter_posts, load_posts
from analyze.toph import ROBLOX_PLATFORMS


def _compact_view(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.0f}M view"
    if absolute >= 1_000:
        return f"{value / 1_000:.0f}K view"
    return f"{int(value)} view"


def _build_daily_view_chart(
    daily_points: list[dict[str, Any]],
    *,
    title: str,
    include_weekday: bool,
    peak_channels: list[dict[str, Any]] | None = None,
    show_peak_channels: bool = True,
    filename_prefix: str,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    dates = [datetime.fromisoformat(str(item["date"])).date() for item in daily_points]
    values = [int(item.get("totalViews", 0) or 0) for item in daily_points]
    if include_weekday:
        labels = [f"{_weekday_label(day.weekday())}\n{day.strftime('%d/%m')}" for day in dates]
    else:
        labels = [day.strftime("%d/%m") for day in dates]

    output_dir = Path(tempfile.mkdtemp(prefix="seatalk-chart-"))
    output_path = output_dir / f"{filename_prefix}.png"

    fig, ax = plt.subplots(figsize=(14, 5.4))
    ax.plot(labels, values, color="#0f6cbd", linewidth=2.6)
    ax.fill_between(labels, values, color="#cfe8ff", alpha=0.45)
    fig.suptitle(title, fontsize=18, fontweight="bold", y=0.99)
    ax.set_ylabel("View", fontsize=12)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: _compact_view(value)))
    ax.grid(axis="y", linestyle="--", linewidth=0.7, alpha=0.35)
    ax.tick_params(axis="x", rotation=45, labelsize=9)
    ax.margins(y=0.16)

    for tick, day in zip(ax.get_xticklabels(), dates):
        if day.weekday() in {5, 6}:
            tick.set_color("#d97706")
            tick.set_fontweight("bold")
        tick.set_ha("right")

    if values:
        peak_index = max(range(len(values)), key=lambda index: values[index])
        peak_value = values[peak_index]
        peak_text = "\n".join(
            f"{index + 1}. {item['channelName']}"
            for index, item in enumerate((peak_channels or [])[:3])
        )
        if peak_text and show_peak_channels:
            ax.annotate(
                peak_text,
                xy=(peak_index, peak_value),
                xytext=(peak_index, peak_value + max(values) * 0.012 if max(values) else 1),
                fontsize=8,
                ha="center",
                va="bottom",
                color="#1f2937",
                arrowprops={"arrowstyle": "-", "color": "#94a3b8", "linewidth": 0.8},
            )

    fig.text(0.965, 0.95, "FFVN", ha="right", va="top", fontsize=9, color="#475569", alpha=0.85)
    fig.subplots_adjust(top=0.8, bottom=0.22)
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    fig.savefig(output_path, format="png", dpi=150)
    plt.close(fig)
    return output_path


def _weekday_label(weekday: int) -> str:
    return {
        0: "Thứ Hai",
        1: "Thứ Ba",
        2: "Thứ Tư",
        3: "Thứ Năm",
        4: "Thứ Sáu",
        5: "Thứ Bảy",
        6: "Chủ Nhật",
    }[weekday]


def build_kol_30d_chart(
    db_path: Path,
    *,
    title: str = "Biểu Đồ View KOLs 30 ngày gần nhất",
    now: datetime | None = None,
) -> Path:
    posts = load_posts(db_path)
    anchor = (now or datetime.now()).date()
    start_date = anchor - timedelta(days=29)
    scoped = filter_posts(
        posts,
        start_date=start_date,
        end_date=anchor,
        platforms=KOL_PLATFORMS,
        category_ids=KOL_CATEGORY_IDS,
        require_kol=True,
    )
    totals: dict[str, int] = {}
    peak_day_channels: dict[tuple[str, str, str], dict[str, Any]] = {}
    peak_day_total = -1
    for offset in range(30):
        day = start_date + timedelta(days=offset)
        day_posts = [post for post in scoped if post.published_date == day]
        day_total = sum(post.view for post in day_posts)
        day_iso = day.isoformat()
        totals[day_iso] = day_total
        if day_total > peak_day_total:
            peak_day_total = day_total
            peak_day_channels = {}
            for post in day_posts:
                key = (post.platform, post.channel_id, post.channel_name)
                entry = peak_day_channels.setdefault(
                    key,
                    {"platform": post.platform, "channelName": post.channel_name, "totalViews": 0},
                )
                entry["totalViews"] = int(entry["totalViews"]) + post.view
    peak_channels = [
        item
        for item in sorted(
            peak_day_channels.values(),
            key=lambda item: (int(item["totalViews"]), str(item["channelName"])),
            reverse=True,
        )[:3]
    ]
    daily_points = [{"date": day_iso, "totalViews": totals[day_iso]} for day_iso in sorted(totals)]
    return _build_daily_view_chart(
        daily_points,
        title=title,
        include_weekday=False,
        peak_channels=peak_channels,
        filename_prefix="kol-30d-chart",
    )


def build_campaign_30d_chart(
    campaign: dict[str, Any],
    *,
    title: str = "Biểu Đồ View Campaign 30 ngày gần nhất",
) -> Path:
    return _build_daily_view_chart(
        list(campaign.get("dailyChart") or []),
        title=title,
        include_weekday=False,
        peak_channels=list((campaign.get("peakDay") or {}).get("topChannels") or []),
        filename_prefix=f"campaign-{campaign.get('campaignName', 'report')}".replace(" ", "-").lower(),
    )


def build_official_30d_chart(
    section: dict[str, Any],
    *,
    title: str = "Biểu Đồ View Official 30 ngày gần nhất",
) -> Path:
    return _build_daily_view_chart(
        list(section.get("dailyChart") or []),
        title=title,
        include_weekday=False,
        peak_channels=list((section.get("peakDay") or {}).get("topChannels") or []),
        show_peak_channels=False,
        filename_prefix="official-30d-chart",
    )


def build_roblox_30d_chart(
    db_path: Path,
    *,
    title: str = "Biểu Đồ View Roblox 30 ngày gần nhất",
    now: datetime | None = None,
) -> Path:
    posts = load_posts(db_path)
    anchor = (now or datetime.now()).date()
    start_date = anchor - timedelta(days=29)
    scoped = filter_posts(
        posts,
        start_date=start_date,
        end_date=anchor,
        platforms=ROBLOX_PLATFORMS,
        category_ids=ROBLOX_CATEGORY_IDS,
    )
    totals: dict[str, int] = {}
    peak_day_channels: dict[tuple[str, str, str], dict[str, Any]] = {}
    peak_day_total = -1
    for offset in range(30):
        day = start_date + timedelta(days=offset)
        day_posts = [post for post in scoped if post.published_date == day]
        day_total = sum(post.view for post in day_posts)
        day_iso = day.isoformat()
        totals[day_iso] = day_total
        if day_total > peak_day_total:
            peak_day_total = day_total
            peak_day_channels = {}
            for post in day_posts:
                key = (post.platform, post.channel_id, post.channel_name)
                entry = peak_day_channels.setdefault(
                    key,
                    {"platform": post.platform, "channelName": post.channel_name, "totalViews": 0},
                )
                entry["totalViews"] = int(entry["totalViews"]) + post.view
    peak_channels = [
        item
        for item in sorted(
            peak_day_channels.values(),
            key=lambda item: (int(item["totalViews"]), str(item["channelName"])),
            reverse=True,
        )[:3]
    ]
    daily_points = [{"date": day_iso, "totalViews": totals[day_iso]} for day_iso in sorted(totals)]
    return _build_daily_view_chart(
        daily_points,
        title=title,
        include_weekday=False,
        peak_channels=peak_channels,
        filename_prefix="roblox-30d-chart",
    )


def build_kol_channel_30d_chart(
    *,
    channel: dict[str, Any],
    daily_chart: list[dict[str, Any]],
    title: str | None = None,
) -> Path:
    channel_name = str(channel.get("channelName") or "-").strip()
    platform = str(channel.get("platform") or "").strip().lower()
    platform_label = {
        "tiktok": "TikTok",
        "youtube": "YouTube",
        "facebook": "Facebook",
    }.get(platform, platform.title() or "KOL")
    chart_title = title or f"Biểu Đồ View kênh {platform_label} 30 ngày - {channel_name}"
    filename_slug = f"kol-channel-{platform}-{channel_name}".replace(" ", "-").replace("/", "-").lower()
    return _build_daily_view_chart(
        list(daily_chart or []),
        title=chart_title,
        include_weekday=False,
        peak_channels=[],
        show_peak_channels=False,
        filename_prefix=filename_slug,
    )


def build_hashtag_30d_chart(
    *,
    hashtag: str,
    daily_chart: list[dict[str, Any]],
    title: str | None = None,
) -> Path:
    normalized_hashtag = str(hashtag or "").strip().lstrip("#")
    chart_title = title or f"Biểu Đồ View hashtag #{normalized_hashtag} 30 ngày"
    filename_slug = f"hashtag-{normalized_hashtag}".replace(" ", "-").replace("/", "-").lower()
    return _build_daily_view_chart(
        list(daily_chart or []),
        title=chart_title,
        include_weekday=False,
        peak_channels=[],
        show_peak_channels=False,
        filename_prefix=filename_slug,
    )
