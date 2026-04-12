from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PRESET_DIR = Path(__file__).resolve().parent.parent / "presets"


@dataclass(slots=True)
class Preset:
    name: str
    data: dict[str, Any]


def preset_path(name: str) -> Path:
    return PRESET_DIR / f"{name}.json"


def load_preset(name: str) -> Preset:
    path = preset_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Preset not found: {name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Preset(name=name, data=data)


def apply_preset_defaults(args: Any, preset: Preset) -> None:
    data = preset.data

    if not getattr(args, "app_slug", "") and data.get("app_slug"):
        args.app_slug = data["app_slug"]
    if getattr(args, "app_id", 0) == 0 and data.get("app_id"):
        args.app_id = data["app_id"]
    if not getattr(args, "category_ids", None) and data.get("category_ids"):
        args.category_ids = list(data["category_ids"])
    if not getattr(args, "platform_ids", None) and data.get("platform_ids"):
        args.platform_ids = list(data["platform_ids"])
    if not getattr(args, "hashtags", None) and data.get("hashtags"):
        args.hashtags = list(data["hashtags"])
    if not getattr(args, "event_hashtags", None) and data.get("event_hashtags"):
        args.event_hashtags = list(data["event_hashtags"])
    if getattr(args, "fetch_window", None) == "7D" and data.get("fetch_window"):
        args.fetch_window = data["fetch_window"]
    if getattr(args, "report_mode", None) == "complete_previous_day" and data.get("report_mode"):
        args.report_mode = data["report_mode"]
    if getattr(args, "report_timezone", None) == "Asia/Ho_Chi_Minh" and data.get("report_timezone"):
        args.report_timezone = data["report_timezone"]
    if getattr(args, "top_limit", None) == 5 and data.get("top_limit"):
        args.top_limit = data["top_limit"]
    if getattr(args, "trend_min_views", None) == 200000 and data.get("trend_min_views"):
        args.trend_min_views = data["trend_min_views"]
    if not getattr(args, "metric_ids", None) and data.get("metric_ids"):
        args.metric_ids = list(data["metric_ids"])
    if getattr(args, "metric_duration", None) == 30 and data.get("metric_duration"):
        args.metric_duration = data["metric_duration"]

    for bool_key in ("use_export", "chunk_by_category", "chunk_by_day", "report"):
        if not getattr(args, bool_key, False) and data.get(bool_key):
            setattr(args, bool_key, True)

    if getattr(args, "seatalk_title", None) == "Datasocial Report" and data.get("seatalk_title"):
        args.seatalk_title = data["seatalk_title"]

    output_prefix = data.get("output_prefix", preset.name)
    if getattr(args, "save_export", None) is None and getattr(args, "use_export", False):
        args.save_export = Path("outputs") / f"{output_prefix}_latest.csv"
    if getattr(args, "save_report", None) is None and (getattr(args, "report", False) or getattr(args, "analyze_only", False)):
        args.save_report = Path("outputs") / f"{output_prefix}_latest.json"

