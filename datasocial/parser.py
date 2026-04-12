from __future__ import annotations

from typing import Any

from .exceptions import GraphQLParseError
from .models import PostPage, PostRecord


def parse_list_post_response(payload: dict[str, Any]) -> PostPage:
    try:
        list_post = payload["data"]["listPost"]
    except KeyError as exc:
        raise GraphQLParseError("Missing data.listPost in GraphQL response.") from exc

    results_payload = list_post.get("results")
    total = list_post.get("total")
    if not isinstance(results_payload, list):
        raise GraphQLParseError("Expected listPost.results to be a list.")
    if not isinstance(total, int):
        raise GraphQLParseError("Expected listPost.total to be an integer.")

    return PostPage(
        total=total,
        results=[normalize_post(item) for item in results_payload],
        raw=payload,
    )


def normalize_post(item: dict[str, Any]) -> PostRecord:
    if not isinstance(item, dict):
        raise GraphQLParseError("Each post item must be an object.")

    title = _first_non_empty(item.get("name"), item.get("alias"), item.get("sub"), "Untitled post")
    url = str(item.get("url") or "")
    created_at = str(item.get("createdAt") or "")
    post_id = str(item.get("id") or url or title)
    metrics = _extract_metrics(item)

    return PostRecord(
        post_id=post_id,
        title=title,
        url=url,
        created_at=created_at,
        metrics=metrics,
        raw=item,
    )


def _extract_metrics(item: dict[str, Any]) -> dict[str, Any]:
    metrics = item.get("metrics")
    if isinstance(metrics, dict):
        return metrics
    fallback_keys = ("view", "like", "comment", "share")
    return {key: item[key] for key in fallback_keys if key in item and item[key] is not None}


def _first_non_empty(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
