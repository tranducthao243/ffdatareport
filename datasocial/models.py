from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class PostRecord:
    post_id: str
    title: str
    url: str
    created_at: str
    metrics: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PostPage:
    total: int
    results: list[PostRecord]
    raw: dict[str, Any]


@dataclass(slots=True)
class ExportRecord:
    row_id: str
    platform: str
    platform_key: str
    channel_id: str
    channel_name: str
    category: str
    post_id: str
    post_type: str
    description: str
    url: str
    published_at: datetime
    hashtags: list[str]
    comment: int
    duration_seconds: int
    engagement: int
    reaction: int
    view: int
    raw: dict[str, Any] = field(default_factory=dict)
