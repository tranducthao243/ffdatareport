from __future__ import annotations

import json

from .models import PostPage


def render_posts(page: PostPage) -> str:
    lines = [f"Total posts: {page.total}"]
    for index, post in enumerate(page.results, start=1):
        metrics = json.dumps(post.metrics, ensure_ascii=False, sort_keys=True)
        lines.extend(
            [
                f"{index}. {post.title}",
                f"   url: {post.url or '-'}",
                f"   createdAt: {post.created_at or '-'}",
                f"   metrics: {metrics}",
            ]
        )
    return "\n".join(lines)


def print_posts(page: PostPage) -> None:
    print(render_posts(page))
