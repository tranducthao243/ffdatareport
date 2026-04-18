from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

from .config import Settings
from .exceptions import GraphQLHTTPError, GraphQLResponseError
from .exporter import (
    DEFAULT_EXPORT_TTL,
    build_daily_windows,
    build_export_filter,
    dedupe_export_rows,
    parse_export_csv,
)
from .graphql import LIST_POST_QUERY, build_list_post_variables

LOGGER = logging.getLogger("datasocial")

EXPORT_DOWNLOAD_RETRY_STATUSES = {502, 503, 504}
EXPORT_DOWNLOAD_MAX_ATTEMPTS = 3
EXPORT_DOWNLOAD_BASE_DELAY_SECONDS = 2.0


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

        LOGGER.info(
            "LIST_POST start | from=%s | to=%s | categories=%s | platforms=%s | channels=%s | page=%s | per_page=%s",
            created_at_gte,
            created_at_lte,
            category_ids,
            platform_ids,
            channel_ids,
            page,
            per_page,
        )

        data = self._post(payload)

        try:
            list_post = data["data"]["listPost"]
            total = list_post.get("total")
            results = list_post.get("results") or []
            LOGGER.info(
                "LIST_POST done | total=%s | returned=%s | page=%s",
                total,
                len(results),
                page,
            )
        except Exception:
            LOGGER.warning("LIST_POST done but response shape unexpected")

        return data

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

        LOGGER.info(
            "LIST_POST_ALL start | from=%s | to=%s | categories=%s | platforms=%s | channels=%s | start_page=%s | per_page=%s | max_pages=%s",
            created_at_gte,
            created_at_lte,
            category_ids,
            platform_ids,
            channel_ids,
            page,
            per_page,
            max_pages,
        )

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

            LOGGER.info(
                "LIST_POST_ALL page done | page=%s | page_results=%s | accumulated=%s | total=%s",
                current_page,
                len(page_results),
                len(results),
                total,
            )

            if len(results) >= total or not page_results:
                break

            if max_pages is not None and pages_fetched >= max_pages:
                LOGGER.info("LIST_POST_ALL stop because reached max_pages=%s", max_pages)
                break

            current_page += 1

        LOGGER.info(
            "LIST_POST_ALL done | pages_fetched=%s | total_results=%s",
            pages_fetched,
            len(results),
        )
        return results

    def export_insight_post_csv(
        self,
        *,
        app_id: int,
        created_at_gte: str | None,
        created_at_lte: str | None,
        category_ids: list[int] | None,
        platform_ids: list[int] | None,
        channel_ids: list[int] | None,
        metric_ids: list[int] | None,
        metric_duration: int,
        ttl: str = DEFAULT_EXPORT_TTL,
    ) -> bytes:
        mutation = """
        mutation ExportInsight($resource: String!, $filter: JSON, $ttl: String!, $appId: UInt32!) {
          exportInsight(resource: $resource, filter: $filter, ttl: $ttl, appId: $appId)
        }
        """.strip()

        export_filter = build_export_filter(
            created_at_gte=created_at_gte,
            created_at_lte=created_at_lte,
            category_ids=category_ids,
            platform_ids=platform_ids,
            channel_ids=channel_ids,
            metric_ids=metric_ids,
            metric_duration=metric_duration,
        )

        LOGGER.info(
            "EXPORT chunk start | from=%s | to=%s | categories=%s | platforms=%s | channels=%s | metrics=%s | metric_duration=%s",
            created_at_gte,
            created_at_lte,
            category_ids,
            platform_ids,
            channel_ids,
            metric_ids,
            metric_duration,
        )

        data = self._post(
            {
                "query": mutation,
                "variables": {
                    "resource": "Post",
                    "appId": app_id,
                    "ttl": ttl,
                    "filter": export_filter,
                },
                "operationName": "ExportInsight",
            }
        )

        download_url = data.get("data", {}).get("exportInsight")
        if not download_url:
            LOGGER.error(
                "EXPORT chunk failed before download_url | from=%s | to=%s | categories=%s | platforms=%s | response=%s",
                created_at_gte,
                created_at_lte,
                category_ids,
                platform_ids,
                data,
            )
            raise GraphQLResponseError(f"exportInsight returned empty payload: {data}")

        if isinstance(download_url, str) and download_url.startswith("/"):
            download_url = f"{self.settings.origin}{download_url}"

        if not isinstance(download_url, str):
            LOGGER.error(
                "EXPORT chunk invalid download_url | from=%s | to=%s | categories=%s | platforms=%s | payload_type=%s | response=%s",
                created_at_gte,
                created_at_lte,
                category_ids,
                platform_ids,
                type(download_url).__name__,
                data,
            )
            raise GraphQLResponseError(f"Unexpected exportInsight payload: {data}")

        LOGGER.info(
            "EXPORT chunk got download_url | from=%s | to=%s | categories=%s | platforms=%s",
            created_at_gte,
            created_at_lte,
            category_ids,
            platform_ids,
        )

        return self._download_export_csv_with_retry(
            download_url,
            created_at_gte=created_at_gte,
            created_at_lte=created_at_lte,
            category_ids=category_ids,
            platform_ids=platform_ids,
        )

    def export_insight_post_rows_by_day_and_platform(
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

        day_windows = build_daily_windows(created_at_gte, created_at_lte)
        platform_chunks = platform_ids or [None]

        for day_start, day_end in day_windows:
            for platform_id in platform_chunks:
                current_platform_ids = None if platform_id is None else [platform_id]

                LOGGER.info(
                    "EXPORT day+platform chunk start | day_start=%s | day_end=%s | categories=%s | platforms=%s",
                    day_start,
                    day_end,
                    category_ids,
                    current_platform_ids,
                )

                csv_bytes = self.export_insight_post_csv(
                    app_id=app_id,
                    created_at_gte=day_start,
                    created_at_lte=day_end,
                    category_ids=category_ids,
                    platform_ids=current_platform_ids,
                    channel_ids=channel_ids,
                    metric_ids=metric_ids,
                    metric_duration=metric_duration,
                    ttl=ttl,
                )

                parsed_rows = parse_export_csv(csv_bytes)
                parsed_rows = self._annotate_export_rows(parsed_rows, category_ids=category_ids)

                LOGGER.info(
                    "EXPORT day+platform chunk parsed | day_start=%s | day_end=%s | row_count=%s | categories=%s | platforms=%s",
                    day_start,
                    day_end,
                    len(parsed_rows),
                    category_ids,
                    current_platform_ids,
                )

                rows.extend(parsed_rows)

        deduped_rows = dedupe_export_rows(rows)

        LOGGER.info(
            "EXPORT day+platform range done | from=%s | to=%s | rows_before=%s | rows_after=%s | categories=%s | platforms=%s",
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
        return self.export_insight_post_rows_by_day_and_platform(
            app_id=app_id,
            created_at_gte=created_at_gte,
            created_at_lte=created_at_lte,
            category_ids=category_ids,
            platform_ids=platform_ids,
            channel_ids=channel_ids,
            metric_ids=metric_ids,
            metric_duration=metric_duration,
            ttl=ttl,
        )

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
                    raise GraphQLResponseError(
                        "chunk_by_day requires created_at_gte and created_at_lte."
                    )

                category_rows = self.export_insight_post_rows_by_day_and_platform(
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
                if platform_ids:
                    category_rows = []
                    for platform_id in platform_ids:
                        current_platform_ids = [platform_id]

                        LOGGER.info(
                            "EXPORT category+platform chunk start | category_id=%s | from=%s | to=%s | platforms=%s",
                            category_id,
                            created_at_gte,
                            created_at_lte,
                            current_platform_ids,
                        )

                        csv_bytes = self.export_insight_post_csv(
                            app_id=app_id,
                            created_at_gte=created_at_gte,
                            created_at_lte=created_at_lte,
                            category_ids=[category_id],
                            platform_ids=current_platform_ids,
                            channel_ids=channel_ids,
                            metric_ids=metric_ids,
                            metric_duration=metric_duration,
                            ttl=ttl,
                        )
                        parsed_rows = parse_export_csv(csv_bytes)
                        category_rows.extend(
                            self._annotate_export_rows(parsed_rows, category_ids=[category_id])
                        )
                else:
                    csv_bytes = self.export_insight_post_csv(
                        app_id=app_id,
                        created_at_gte=created_at_gte,
                        created_at_lte=created_at_lte,
                        category_ids=[category_id],
                        platform_ids=None,
                        channel_ids=channel_ids,
                        metric_ids=metric_ids,
                        metric_duration=metric_duration,
                        ttl=ttl,
                    )
                    category_rows = parse_export_csv(csv_bytes)
                    category_rows = self._annotate_export_rows(
                        category_rows,
                        category_ids=[category_id],
                    )

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

    @staticmethod
    def _annotate_export_rows(
        rows: list[dict[str, str]],
        *,
        category_ids: list[int] | None,
    ) -> list[dict[str, str]]:
        if not category_ids or len(category_ids) != 1:
            return rows
        category_id = str(category_ids[0])
        for row in rows:
            row.setdefault("__category_id", category_id)
        return rows

    def _download_export_csv_with_retry(
        self,
        download_url: str,
        *,
        created_at_gte: str | None,
        created_at_lte: str | None,
        category_ids: list[int] | None,
        platform_ids: list[int] | None,
    ) -> bytes:
        last_error: Exception | None = None

        for attempt in range(1, EXPORT_DOWNLOAD_MAX_ATTEMPTS + 1):
            LOGGER.info(
                "EXPORT chunk downloading CSV | timeout=%s | attempt=%s/%s | from=%s | to=%s | categories=%s | platforms=%s",
                self.settings.timeout,
                attempt,
                EXPORT_DOWNLOAD_MAX_ATTEMPTS,
                created_at_gte,
                created_at_lte,
                category_ids,
                platform_ids,
            )

            try:
                response = self.session.get(download_url, timeout=self.settings.timeout)
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= EXPORT_DOWNLOAD_MAX_ATTEMPTS:
                    LOGGER.error(
                        "EXPORT chunk download request exception | attempt=%s/%s | from=%s | to=%s | categories=%s | platforms=%s | error=%s",
                        attempt,
                        EXPORT_DOWNLOAD_MAX_ATTEMPTS,
                        created_at_gte,
                        created_at_lte,
                        category_ids,
                        platform_ids,
                        exc,
                    )
                    break

                delay_seconds = EXPORT_DOWNLOAD_BASE_DELAY_SECONDS * attempt
                LOGGER.warning(
                    "EXPORT chunk download request exception, retrying | attempt=%s/%s | delay=%.1fs | from=%s | to=%s | categories=%s | platforms=%s | error=%s",
                    attempt,
                    EXPORT_DOWNLOAD_MAX_ATTEMPTS,
                    delay_seconds,
                    created_at_gte,
                    created_at_lte,
                    category_ids,
                    platform_ids,
                    exc,
                )
                time.sleep(delay_seconds)
                continue

            LOGGER.info(
                "EXPORT chunk download response | status=%s | bytes=%s | from=%s | to=%s | categories=%s | platforms=%s",
                response.status_code,
                len(response.content or b""),
                created_at_gte,
                created_at_lte,
                category_ids,
                platform_ids,
            )

            if response.ok:
                return response.content

            body_preview = response.text[:500]
            last_error = GraphQLHTTPError(
                f"Export download failed with HTTP {response.status_code}: {body_preview}"
            )

            if (
                response.status_code not in EXPORT_DOWNLOAD_RETRY_STATUSES
                or attempt >= EXPORT_DOWNLOAD_MAX_ATTEMPTS
            ):
                LOGGER.error(
                    "EXPORT chunk download failed | status=%s | attempt=%s/%s | from=%s | to=%s | categories=%s | platforms=%s | body_preview=%s",
                    response.status_code,
                    attempt,
                    EXPORT_DOWNLOAD_MAX_ATTEMPTS,
                    created_at_gte,
                    created_at_lte,
                    category_ids,
                    platform_ids,
                    body_preview,
                )
                break

            delay_seconds = EXPORT_DOWNLOAD_BASE_DELAY_SECONDS * attempt
            LOGGER.warning(
                "EXPORT chunk download got retryable status, retrying | status=%s | attempt=%s/%s | delay=%.1fs | from=%s | to=%s | categories=%s | platforms=%s",
                response.status_code,
                attempt,
                EXPORT_DOWNLOAD_MAX_ATTEMPTS,
                delay_seconds,
                created_at_gte,
                created_at_lte,
                category_ids,
                platform_ids,
            )
            time.sleep(delay_seconds)

        if isinstance(last_error, GraphQLHTTPError):
            raise last_error
        if last_error is not None:
            raise GraphQLHTTPError(f"Export download failed after retries: {last_error}")
        raise GraphQLHTTPError("Export download failed after retries with unknown error.")

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        operation_name = payload.get("operationName", "UnknownOperation")
        LOGGER.info("GRAPHQL start | operation=%s", operation_name)

        response = self.session.post(
            self.settings.endpoint,
            data=json.dumps(payload),
            timeout=self.settings.timeout,
        )

        LOGGER.info(
            "GRAPHQL response | operation=%s | status=%s",
            operation_name,
            response.status_code,
        )

        if not response.ok:
            LOGGER.error(
                "GRAPHQL failed | operation=%s | status=%s | body_preview=%s",
                operation_name,
                response.status_code,
                response.text[:500],
            )
            raise GraphQLHTTPError(
                f"GraphQL request failed with HTTP {response.status_code}: {response.text[:500]}"
            )

        data = response.json()

        if data.get("errors"):
            LOGGER.error(
                "GRAPHQL logical errors | operation=%s | errors=%s",
                operation_name,
                data["errors"],
            )
            raise GraphQLResponseError(str(data["errors"]))

        LOGGER.info("GRAPHQL done | operation=%s", operation_name)
        return data
