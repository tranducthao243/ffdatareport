from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from analyze.common import KOL_CATEGORY_IDS, KOL_PLATFORMS, filter_posts, load_posts


def build_kol_30d_chart(db_path: Path, *, title: str = "KOL Daily Views 30 Days", now: datetime | None = None) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

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
    labels = []
    values = []
    current = start_date
    while current <= anchor:
        key = current.isoformat()
        labels.append(current.strftime("%d/%m"))
        values.append(totals.get(key, 0))
        current += timedelta(days=1)

    output_dir = Path(tempfile.mkdtemp(prefix="seatalk-chart-"))
    output_path = output_dir / "kol-30d-chart.png"
    plt.figure(figsize=(10, 4))
    plt.plot(labels, values, color="#0f6cbd", linewidth=2)
    plt.fill_between(labels, values, color="#cfe8ff", alpha=0.45)
    plt.title(title)
    plt.ylabel("Views")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, format="png", dpi=150)
    plt.close()
    return output_path
