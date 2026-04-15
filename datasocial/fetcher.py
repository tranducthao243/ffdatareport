from __future__ import annotations
import json
import logging
from typing import Any
import requests
LOGGER = logging.getLogger("datasocial")
from .config import Settings
from .exceptions import GraphQLHTTPError, GraphQLResponseError
from .exporter import (
    DEFAULT_EXPORT_TTL,
    build_export_filter,
    build_daily_windows,
    dedupe_export_rows,
    parse_export_csv,
)
from .graphql import LIST_POST_QUERY, build_list_post_variables


class GraphQLClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "*/*",
                "Content-Type": "application/json",
                "Origin": settings.origin,
                "Referer": settings.referer,
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                ),
            }
        )
        if settings.usession:
            self.session.cookies.set(
                "usession",
                settings.usession,
                domain="socialdata.garena.vn",
                path="/",
            )

    def list_posts(
        self,
        *,
        app_id: int,
        created_at_gte: str | None,
        created_at_lte: str | None,
        category_ids: list[int] | None,
        platform_ids: list[int] | None,
        channel_ids: list[int] | None,
        page: int,
        per_page: int,
    ) -> dict[str, Any]:
        payload = {
            "query": LIST_POST_QUERY,
            "variables": build_list_post_variables(
                app_id=app_id,
                created_at_gte=created_at_gte,
                created_at_lte=created_at_lte,
                category_ids=category_ids,
                platform_ids=platform_ids,
                channel_ids=channel_ids,
                page=page,
                per_page=per_page,
            ),
            "operationName": "ListPost",
        }
        return self._post(payload)

    def list_posts_all_pages(
        self,
        *,
        app_id: int,
        created_at_gte: str | None,
        created_at_lte: str | None,
        category_ids: list[int] | None,
        platform_ids: list[int] | None,
        channel_ids: list[int] | None,
        page: int,
        per_page: int,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        current_page = page
        pages_fetched = 0

        while True:
            payload = self.list_posts(
                app_id=app_id,
                created_at_gte=created_at_gte,
                created_at_lte=created_at_lte,
                category_ids=category_ids,
                platform_ids=platform_ids,
                channel_ids=channel_ids,
                page=current_page,
                per_page=per_page,
            )
            list_post = payload["data"]["listPost"]
            page_results = list_post.get("results") or []
            results.extend(page_results)

            pages_fetched += 1
            total = list_post.get("total") or 0
            if len(results) >= total or not page_results:
                break
            if max_pages is not None and pages_fetched >= max_pages:
                break
            current_page += 1

        return results

    def export_insight_post_rows_by_day(
    self,
    *,
    app_id: int,
    created_at_gte: str,
    created_at_lte: str,
    category_ids: list[int] | None,
    platform_ids: list[int] | None,
    channel_ids: list[int] | None,
    metric_ids: list[int] | None,
    metric_duration: int,
    ttl: str = DEFAULT_EXPORT_TTL,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for day_start, day_end in build_daily_windows(created_at_gte, created_at_lte):
        LOGGER.info(
            "EXPORT day chunk | day_start=%s | day_end=%s | categories=%s | platforms=%s",
            day_start,
            day_end,
            category_ids,
            platform_ids,
        )
        csv_bytes = self.export_insight_post_csv(
            app_id=app_id,
            created_at_gte=day_start,
            created_at_lte=day_end,
            category_ids=category_ids,
            platform_ids=platform_ids,
            channel_ids=channel_ids,
            metric_ids=metric_ids,
            metric_duration=metric_duration,
            ttl=ttl,
        )
        parsed_rows = parse_export_csv(csv_bytes)
        LOGGER.info(
            "EXPORT day chunk parsed | day_start=%s | day_end=%s | row_count=%s | categories=%s | platforms=%s",
            day_start,
            day_end,
            len(parsed_rows),
            category_ids,
            platform_ids,
        )
        rows.extend(parsed_rows)

    deduped_rows = dedupe_export_rows(rows)
    LOGGER.info(
        "EXPORT day chunk deduped total | from=%s | to=%s | rows_before=%s | rows_after=%s | categories=%s | platforms=%s",
        created_at_gte,
        created_at_lte,
        len(rows),
        len(deduped_rows),
        category_ids,
        platform_ids,
    )
    return deduped_rows

    def export_insight_post_rows_by_day(
        self,
        *,
        app_id: int,
        created_at_gte: str,
        created_at_lte: str,
        category_ids: list[int] | None,
        platform_ids: list[int] | None,
        channel_ids: list[int] | None,
        metric_ids: list[int] | None,
        metric_duration: int,
        ttl: str = DEFAULT_EXPORT_TTL,
    ) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for day_start, day_end in build_daily_windows(created_at_gte, created_at_lte):
            csv_bytes = self.export_insight_post_csv(
                app_id=app_id,
                created_at_gte=day_start,
                created_at_lte=day_end,
                category_ids=category_ids,
                platform_ids=platform_ids,
                channel_ids=channel_ids,
                metric_ids=metric_ids,
                metric_duration=metric_duration,
                ttl=ttl,
            )
            rows.extend(parse_export_csv(csv_bytes))
        return dedupe_export_rows(rows)

    def export_insight_post_rows_by_category(
    self,
    *,
    app_id: int,
    created_at_gte: str | None,
    created_at_lte: str | None,
    category_ids: list[int],
    platform_ids: list[int] | None,
    channel_ids: list[int] | None,
    metric_ids: list[int] | None,
    metric_duration: int,
    ttl: str = DEFAULT_EXPORT_TTL,
    chunk_by_day: bool = False,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    LOGGER.info(
        "EXPORT by category start | from=%s | to=%s | category_ids=%s | platform_ids=%s | chunk_by_day=%s",
        created_at_gte,
        created_at_lte,
        category_ids,
        platform_ids,
        chunk_by_day,
    )

    for category_id in category_ids:
        LOGGER.info(
            "EXPORT category chunk start | category_id=%s | from=%s | to=%s | platforms=%s",
            category_id,
            created_at_gte,
            created_at_lte,
            platform_ids,
        )

        if chunk_by_day:
            if not created_at_gte or not created_at_lte:
                raise GraphQLResponseError("chunk_by_day requires created_at_gte and created_at_lte.")

            category_rows = self.export_insight_post_rows_by_day(
                app_id=app_id,
                created_at_gte=created_at_gte,
                created_at_lte=created_at_lte,
                category_ids=[category_id],
                platform_ids=platform_ids,
                channel_ids=channel_ids,
                metric_ids=metric_ids,
                metric_duration=metric_duration,
                ttl=ttl,
            )
        else:
            csv_bytes = self.export_insight_post_csv(
                app_id=app_id,
                created_at_gte=created_at_gte,
                created_at_lte=created_at_lte,
                category_ids=[category_id],
                platform_ids=platform_ids,
                channel_ids=channel_ids,
                metric_ids=metric_ids,
                metric_duration=metric_duration,
                ttl=ttl,
            )
            category_rows = parse_export_csv(csv_bytes)

        LOGGER.info(
            "EXPORT category chunk done | category_id=%s | rows=%s | platforms=%s",
            category_id,
            len(category_rows),
            platform_ids,
        )
        rows.extend(category_rows)

    deduped_rows = dedupe_export_rows(rows)
    LOGGER.info(
        "EXPORT by category done | total_rows_before=%s | total_rows_after=%s",
        len(rows),
        len(deduped_rows),
    )
    return deduped_rows

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            self.settings.endpoint,
            data=json.dumps(payload),
            timeout=self.settings.timeout,
        )
        if not response.ok:
            raise GraphQLHTTPError(
                f"GraphQL request failed with HTTP {response.status_code}: {response.text[:500]}"
            )
        data = response.json()
        if data.get("errors"):
            raise GraphQLResponseError(str(data["errors"]))
        return data
