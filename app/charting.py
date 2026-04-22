from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from analyze.common import KOL_CATEGORY_IDS, KOL_PLATFORMS, filter_posts, load_posts


WEEKDAY_LABELS = {
    0: "Thứ Hai",
    1: "Thứ Ba",
    2: "Thứ Tư",
    3: "Thứ Năm",
    4: "Thứ Sáu",
    5: "Thứ Bảy",
    6: "Chủ Nhật",
}


def build_kol_30d_chart(
    db_path: Path,
    *,
    title: str = "Biểu Đồ View KOLs 30 ngày gần nhất",
    now: datetime | None = None,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

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
    for post in scoped:
        key = post.published_date.isoformat()
        totals[key] = totals.get(key, 0) + post.view

    labels: list[str] = []
    values: list[int] = []
    current = start_date
    while current <= anchor:
        key = current.isoformat()
        labels.append(f"{WEEKDAY_LABELS[current.weekday()]}\n{current.strftime('%d/%m')}")
        values.append(totals.get(key, 0))
        current += timedelta(days=1)

    def _format_view_axis(value: float, _position: int) -> str:
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.0f}M view"
        if abs(value) >= 1_000:
            return f"{value / 1_000:.0f}K view"
        return f"{int(value)} view"

    output_dir = Path(tempfile.mkdtemp(prefix="seatalk-chart-"))
    output_path = output_dir / "kol-30d-chart.png"

    plt.figure(figsize=(14, 5))
    plt.plot(labels, values, color="#0f6cbd", linewidth=2.6)
    plt.fill_between(labels, values, color="#cfe8ff", alpha=0.45)
    plt.title(title, fontsize=18, fontweight="bold")
    plt.ylabel("View", fontsize=12)
    plt.gca().yaxis.set_major_formatter(FuncFormatter(_format_view_axis))
    plt.xticks(rotation=45, ha="right", fontsize=9)
    plt.grid(axis="y", linestyle="--", linewidth=0.7, alpha=0.35)
    plt.tight_layout()
    plt.savefig(output_path, format="png", dpi=150)
    plt.close()
    return output_path
