from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import sys

from app.pipeline import build_configured_reports, build_store_from_export
from .analysis import build_report
from .config import DEFAULT_APP_ID, DEFAULT_PER_PAGE, Settings
from .display import print_posts
from .exceptions import DatasocialError
from .exporter import (
    DEFAULT_EXPORT_METRIC_DURATION,
    DEFAULT_EXPORT_METRIC_IDS,
    build_export_report,
    export_rows_to_csv_bytes,
    parse_export_csv,
)
from .formatter import render_report, render_seatalk_report
from .fetcher import GraphQLClient
from .parser import normalize_post, parse_list_post_response
from .presets import apply_preset_defaults, load_preset
from .seatalk import SeaTalkClient, SeaTalkSettings
from .timewindows import DEFAULT_REPORT_TZ, build_date_window


LOGGER = logging.getLogger("datasocial")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datasocial",
        description="Fetch, normalize, analyze, and deliver private Social Data reports.",
    )
    parser.add_argument("--endpoint", help="Override GraphQL endpoint.")
    parser.add_argument("--preset", help="Load a JSON preset from the presets directory, e.g. ffvn_daily.")
    parser.add_argument("--usession", help="Auth cookie value. Falls back to DATASOCIAL_USESSION.")
    parser.add_argument("--app-slug", help="App slug used to mimic browser referer, e.g. ffvn.")
    parser.add_argument(
        "--app-id",
        type=int,
        default=DEFAULT_APP_ID,
        help="Required GraphQL appId. Falls back to DATASOCIAL_APP_ID.",
    )
    parser.add_argument("--created-at-gte", help="Lower bound for createdAt filter. Auto-computed when omitted.")
    parser.add_argument("--created-at-lte", help="Upper bound for createdAt filter. Auto-computed when omitted.")
    parser.add_argument(
        "--report-mode",
        choices=["complete_previous_day", "today_so_far"],
        default="complete_previous_day",
        help="Anchor rolling windows to the previous full day or include today_so_far.",
    )
    parser.add_argument(
        "--fetch-window",
        choices=["1D", "4D", "7D", "30D"],
        default="7D",
        help="Maximum automatic fetch window when explicit dates are not provided.",
    )
    parser.add_argument(
        "--report-timezone",
        default=DEFAULT_REPORT_TZ,
        help="Timezone used for dynamic windows and export normalization.",
    )
    parser.add_argument("--page", type=int, default=0, help="Zero-based page number.")
    parser.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE, help="Page size.")
    parser.add_argument("--all-pages", action="store_true", help="Fetch all pages from listPost.")
    parser.add_argument("--max-pages", type=int, help="Optional cap when using --all-pages.")
    parser.add_argument("--report", action="store_true", help="Generate a report instead of printing raw posts.")
    parser.add_argument("--fetch-only", action="store_true", help="Fetch data only, do not analyze.")
    parser.add_argument("--analyze-only", action="store_true", help="Analyze previously saved export data only.")
    parser.add_argument("--use-export", action="store_true", help="Use exportInsight for richer reporting data.")
    parser.add_argument("--chunk-by-day", action="store_true", help="Split export fetch into daily windows.")
    parser.add_argument("--chunk-by-category", action="store_true", help="Split export fetch by category id.")
    parser.add_argument(
        "--category-id",
        type=int,
        action="append",
        dest="category_ids",
        help="Repeatable category filter.",
    )
    parser.add_argument(
        "--platform-id",
        type=int,
        action="append",
        dest="platform_ids",
        help="Repeatable channel platform filter.",
    )
    parser.add_argument(
        "--channel-id",
        type=int,
        action="append",
        dest="channel_ids",
        help="Repeatable channel filter.",
    )
    parser.add_argument("--hashtag", action="append", dest="hashtags", help="Repeatable hashtag filter.")
    parser.add_argument(
        "--event-hashtag",
        action="append",
        dest="event_hashtags",
        help="Repeatable event hashtag filter. Reserved for future campaign module metadata.",
    )
    parser.add_argument("--top-limit", type=int, default=5, help="Limit per ranked report section.")
    parser.add_argument(
        "--trend-min-views",
        type=int,
        default=200000,
        help="Minimum views required for 7D abnormal trend videos.",
    )
    parser.add_argument(
        "--metric-id",
        type=int,
        action="append",
        dest="metric_ids",
        help="Repeatable export metric id. Defaults to the metric set captured from the web UI.",
    )
    parser.add_argument(
        "--metric-duration",
        type=int,
        default=DEFAULT_EXPORT_METRIC_DURATION,
        help="Metric duration for exportInsight.",
    )
    parser.add_argument("--send-seatalk", action="store_true", help="Send the generated report to SeaTalk.")
    parser.add_argument("--seatalk-group-id", help="Override SeaTalk target group id.")
    parser.add_argument("--seatalk-employee-code", help="Override SeaTalk target employee code.")
    parser.add_argument("--seatalk-title", default="Datasocial Report", help="SeaTalk message title.")
    parser.add_argument("--save-raw", type=Path, help="Optional path to save raw API JSON.")
    parser.add_argument("--save-export", type=Path, help="Optional path to save exported CSV bytes.")
    parser.add_argument("--load-export", type=Path, help="Load a previously saved export CSV for analyze-only mode.")
    parser.add_argument("--save-store", type=Path, help="Optional path to save normalized SQLite store.")
    parser.add_argument("--load-store", type=Path, help="Load a previously built normalized SQLite store.")
    parser.add_argument("--build-master-store", action="store_true", help="Build the normalized SQLite data layer from an export CSV.")
    parser.add_argument("--build-configured-reports", action="store_true", help="Build config-driven report packages from SQLite.")
    parser.add_argument("--groups-config", type=Path, default=Path("config/groups.json"), help="Groups config JSON path.")
    parser.add_argument("--reports-config", type=Path, default=Path("config/reports.json"), help="Reports config JSON path.")
    parser.add_argument("--campaigns-config", type=Path, default=Path("config/campaigns.json"), help="Campaigns config JSON path.")
    parser.add_argument("--save-report", type=Path, help="Optional path to save report JSON.")
    parser.add_argument(
        "--save-rendered-dir",
        type=Path,
        help="Optional directory to save rendered Seatalk text previews for each configured report package.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging.")
    parser.add_argument("--log-file", type=Path, help="Optional path to write runtime logs.")
    parser.add_argument("--status-file", type=Path, help="Optional path to write runtime status JSON.")
    return parser


def configure_logging(debug: bool, log_file: Path | None) -> None:
    level = logging.DEBUG if debug else logging.INFO
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def write_status(status_file: Path | None, status: dict) -> None:
    if not status_file:
        return
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def update_status(status: dict, phase: str, **fields: object) -> None:
    status["phase"] = phase
    status["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    for key, value in fields.items():
        status[key] = value


def slugify_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return normalized or "report"


def parse_admin_employee_codes() -> list[str]:
    raw_values = [
        os.getenv("SEATALK_ADMIN_EMPLOYEE_CODES", ""),
        os.getenv("SEATALK_ADMIN_EMPLOYEE_CODE", ""),
    ]
    results: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for token in raw.replace(";", ",").split(","):
            value = token.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            results.append(value)
    return results


def persist_rendered_packages(rendered_dir: Path | None, payload: dict) -> list[str]:
    if not rendered_dir:
        return []

    rendered_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[str] = []
    for package in payload.get("packages", []):
        rendered_text = str(package.get("renderedText") or "").strip()
        if not rendered_text:
            continue
        preview_text = rendered_text
        interactive_actions = package.get("interactiveActions") or []
        if interactive_actions:
            lines = [preview_text, "", "Interactive actions (planned):"]
            for action in interactive_actions:
                lines.append(
                    f"- {action.get('label', '-')}: {action.get('targetReportCode', '-')}"
                )
                lines.append(f"  callback_payload: {action.get('callbackPayload', '')}")
            preview_text = "\n".join(lines).strip()
        file_name = f"{slugify_filename(package.get('groupName', 'report'))}.txt"
        path = rendered_dir / file_name
        path.write_text(preview_text + "\n", encoding="utf-8")
        saved_paths.append(str(path))
    return saved_paths


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except OSError:
            pass

    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.debug, args.log_file)

    status: dict[str, object] = {
        "phase": "init",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "event_name": os.getenv("GITHUB_EVENT_NAME", ""),
        "run_id": os.getenv("GITHUB_RUN_ID", ""),
        "run_number": os.getenv("GITHUB_RUN_NUMBER", ""),
        "job": os.getenv("GITHUB_JOB", ""),
        "send_seatalk": bool(args.send_seatalk),
        "analyze_only": bool(args.analyze_only),
        "fetch_only": bool(args.fetch_only),
        "use_export": bool(args.use_export),
    }
    write_status(args.status_file, status)

    if args.preset:
        try:
            preset = load_preset(args.preset)
        except FileNotFoundError as exc:
            parser.exit(status=1, message=f"datasocial error: {exc}\n")
        apply_preset_defaults(args, preset)

    settings = Settings.from_env()
    if args.endpoint:
        settings.endpoint = args.endpoint
    if args.usession:
        settings.usession = args.usession
    if args.app_slug:
        settings.app_slug = args.app_slug
    if args.app_id != DEFAULT_APP_ID:
        settings.app_id = args.app_id
    if args.seatalk_group_id:
        settings.seatalk_group_id = args.seatalk_group_id
    if args.seatalk_employee_code:
        settings.seatalk_employee_code = args.seatalk_employee_code

    local_only_mode = args.analyze_only or args.build_master_store or args.build_configured_reports
    if settings.app_id <= 0 and not local_only_mode:
        parser.exit(status=1, message="datasocial error: appId is required.\n")

    if args.fetch_only and args.analyze_only:
        parser.exit(status=1, message="datasocial error: choose only one of --fetch-only or --analyze-only.\n")
    if args.build_master_store and not args.load_export:
        parser.exit(status=1, message="datasocial error: --build-master-store requires --load-export.\n")
    if args.build_configured_reports and not args.load_store:
        parser.exit(status=1, message="datasocial error: --build-configured-reports requires --load-store.\n")

    if not args.created_at_gte or not args.created_at_lte:
        auto_window = build_date_window(
            args.fetch_window,
            mode=args.report_mode,
            timezone_name=args.report_timezone,
        )
        args.created_at_gte = args.created_at_gte or auto_window.start_date
        args.created_at_lte = args.created_at_lte or auto_window.end_date

    client = GraphQLClient(settings)

    try:
        update_status(
            status,
            "window_resolved",
            created_at_gte=args.created_at_gte,
            created_at_lte=args.created_at_lte,
            report_timezone=args.report_timezone,
            fetch_window=args.fetch_window,
            report_mode=args.report_mode,
        )
        write_status(args.status_file, status)
        LOGGER.info(
            "Resolved window: %s -> %s (%s, mode=%s)",
            args.created_at_gte,
            args.created_at_lte,
            args.report_timezone,
            args.report_mode,
        )

        if args.build_master_store:
            update_status(status, "build_master_store", load_export=str(args.load_export), save_store=str(args.save_store))
            write_status(args.status_file, status)
            summary = build_store_from_export(
                args.load_export,
                args.save_store,
                timezone_name=args.report_timezone,
            )
            if args.save_report:
                args.save_report.parent.mkdir(parents=True, exist_ok=True)
                args.save_report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            update_status(status, "completed", exit_code=0, store_summary=summary)
            write_status(args.status_file, status)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        if args.build_configured_reports:
            update_status(status, "build_configured_reports", load_store=str(args.load_store))
            write_status(args.status_file, status)
            payload = build_configured_reports(
                args.load_store,
                groups_path=args.groups_config,
                reports_path=args.reports_config,
                campaigns_path=args.campaigns_config,
                timezone_name=args.report_timezone,
                mode=args.report_mode,
                source_scope={
                    "category_ids": list(args.category_ids or []),
                    "platform_ids": list(args.platform_ids or []),
                },
                send=args.send_seatalk,
                seatalk_app_id=settings.seatalk_app_id,
                seatalk_app_secret=settings.seatalk_app_secret,
                seatalk_admin_employee_codes=parse_admin_employee_codes(),
            )
            if args.save_report:
                args.save_report.parent.mkdir(parents=True, exist_ok=True)
                args.save_report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            rendered_paths = persist_rendered_packages(args.save_rendered_dir, payload)
            if rendered_paths:
                LOGGER.info("Saved %s rendered report preview(s) to %s", len(rendered_paths), args.save_rendered_dir)
            update_status(status, "completed", exit_code=0, package_count=payload.get("packageCount", 0))
            write_status(args.status_file, status)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.analyze_only:
            if not args.load_export:
                parser.exit(status=1, message="datasocial error: --analyze-only requires --load-export.\n")
            update_status(status, "analyze_only_load_export", load_export=str(args.load_export))
            write_status(args.status_file, status)
            LOGGER.info("Analyze-only mode with export file: %s", args.load_export)
            export_rows = parse_export_csv(args.load_export.read_bytes())
            report = build_export_report(
                export_rows,
                hashtag_filters=args.hashtags,
                event_hashtags=args.event_hashtags,
                report_mode=args.report_mode,
                timezone_name=args.report_timezone,
                fetch_window_label=args.fetch_window,
                top_limit=args.top_limit,
                trend_min_views=args.trend_min_views,
            )
            update_status(status, "analyze_only_report_ready", export_rows=len(export_rows))
            write_status(args.status_file, status)
            if args.send_seatalk:
                update_status(status, "seatalk_sending")
                write_status(args.status_file, status)
            persist_and_send(args, settings, report)
            update_status(status, "completed", exit_code=0)
            write_status(args.status_file, status)
            print(render_report(report))
            return 0

        if args.use_export and (args.report or args.fetch_only):
            update_status(status, "fetch_export_rows")
            write_status(args.status_file, status)
            export_rows = fetch_export_rows(args, settings, client, parser)
            update_status(status, "export_rows_ready", export_rows=len(export_rows))
            write_status(args.status_file, status)
            LOGGER.info("Fetched export rows: %s", len(export_rows))
            if args.save_export:
                args.save_export.parent.mkdir(parents=True, exist_ok=True)
                args.save_export.write_bytes(export_rows_to_csv_bytes(export_rows))
                LOGGER.info("Saved export CSV to %s", args.save_export)
            if args.fetch_only:
                update_status(status, "completed", exit_code=0)
                write_status(args.status_file, status)
                print(f"Fetched export rows: {len(export_rows)}")
                return 0

            report = build_export_report(
                export_rows,
                hashtag_filters=args.hashtags,
                event_hashtags=args.event_hashtags,
                report_mode=args.report_mode,
                timezone_name=args.report_timezone,
                fetch_window_label=args.fetch_window,
                top_limit=args.top_limit,
                trend_min_views=args.trend_min_views,
            )
            if args.send_seatalk:
                update_status(status, "seatalk_sending")
                write_status(args.status_file, status)
            persist_and_send(args, settings, report)
            update_status(status, "completed", exit_code=0)
            write_status(args.status_file, status)
            print(render_report(report))
            return 0

        update_status(status, "fetch_listpost_payload")
        write_status(args.status_file, status)
        payload = fetch_listpost_payload(args, settings, client)
        post_total = payload.get("data", {}).get("listPost", {}).get("total")
        update_status(status, "listpost_ready", listpost_total=post_total)
        write_status(args.status_file, status)
        LOGGER.info("Fetched listPost payload. total=%s", post_total)
        if args.save_raw:
            args.save_raw.parent.mkdir(parents=True, exist_ok=True)
            args.save_raw.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            LOGGER.info("Saved raw payload to %s", args.save_raw)

        if args.report:
            report = build_report(
                [normalize_post(item) for item in payload["data"]["listPost"]["results"]],
                hashtag_filters=args.hashtags,
                top_limit=args.top_limit,
                event_hashtags=args.event_hashtags,
            )
            if args.send_seatalk:
                update_status(status, "seatalk_sending")
                write_status(args.status_file, status)
            persist_and_send(args, settings, report)
            update_status(status, "completed", exit_code=0)
            write_status(args.status_file, status)
            print(render_report(report))
            return 0

        page = parse_list_post_response(payload)
        update_status(status, "completed", exit_code=0, parsed_posts=len(page.results))
        write_status(args.status_file, status)
        print_posts(page)
        return 0
    except DatasocialError as exc:
        update_status(status, "failed", exit_code=1, error=f"{type(exc).__name__}: {exc}")
        write_status(args.status_file, status)
        LOGGER.exception("DatasocialError")
        parser.exit(status=1, message=f"datasocial error: {exc}\n")
    except OSError as exc:
        update_status(status, "failed", exit_code=1, error=f"{type(exc).__name__}: {exc}")
        write_status(args.status_file, status)
        LOGGER.exception("OSError")
        parser.exit(status=1, message=f"datasocial file error: {exc}\n")
    except Exception as exc:
        update_status(status, "failed", exit_code=1, error=f"{type(exc).__name__}: {exc}")
        write_status(args.status_file, status)
        LOGGER.exception("Unexpected error")
        raise


def fetch_export_rows(args: argparse.Namespace, settings: Settings, client: GraphQLClient, parser: argparse.ArgumentParser) -> list[dict[str, str]]:
    if args.chunk_by_day and (not args.created_at_gte or not args.created_at_lte):
        parser.exit(status=1, message="datasocial error: --chunk-by-day requires a resolved date window.\n")

    if args.chunk_by_category:
        if not args.category_ids:
            parser.exit(status=1, message="datasocial error: --chunk-by-category requires --category-id.\n")
        return client.export_insight_post_rows_by_category(
            app_id=settings.app_id,
            created_at_gte=args.created_at_gte,
            created_at_lte=args.created_at_lte,
            category_ids=args.category_ids,
            platform_ids=args.platform_ids,
            channel_ids=args.channel_ids,
            metric_ids=args.metric_ids or DEFAULT_EXPORT_METRIC_IDS,
            metric_duration=args.metric_duration,
            chunk_by_day=args.chunk_by_day,
        )

    if args.chunk_by_day:
        return client.export_insight_post_rows_by_day(
            app_id=settings.app_id,
            created_at_gte=args.created_at_gte,
            created_at_lte=args.created_at_lte,
            category_ids=args.category_ids,
            platform_ids=args.platform_ids,
            channel_ids=args.channel_ids,
            metric_ids=args.metric_ids or DEFAULT_EXPORT_METRIC_IDS,
            metric_duration=args.metric_duration,
        )

    export_bytes = client.export_insight_post_csv(
        app_id=settings.app_id,
        created_at_gte=args.created_at_gte,
        created_at_lte=args.created_at_lte,
        category_ids=args.category_ids,
        platform_ids=args.platform_ids,
        channel_ids=args.channel_ids,
        metric_ids=args.metric_ids or DEFAULT_EXPORT_METRIC_IDS,
        metric_duration=args.metric_duration,
    )
    return parse_export_csv(export_bytes)


def fetch_listpost_payload(args: argparse.Namespace, settings: Settings, client: GraphQLClient) -> dict:
    if args.all_pages or args.report:
        raw_results = client.list_posts_all_pages(
            app_id=settings.app_id,
            created_at_gte=args.created_at_gte,
            created_at_lte=args.created_at_lte,
            category_ids=args.category_ids,
            platform_ids=args.platform_ids,
            channel_ids=args.channel_ids,
            page=args.page,
            per_page=args.per_page,
            max_pages=args.max_pages,
        )
        return {"data": {"listPost": {"total": len(raw_results), "results": raw_results}}}
    return client.list_posts(
        app_id=settings.app_id,
        created_at_gte=args.created_at_gte,
        created_at_lte=args.created_at_lte,
        category_ids=args.category_ids,
        platform_ids=args.platform_ids,
        channel_ids=args.channel_ids,
        page=args.page,
        per_page=args.per_page,
    )


def persist_and_send(args: argparse.Namespace, settings: Settings, report: dict) -> None:
    if args.save_report:
        args.save_report.parent.mkdir(parents=True, exist_ok=True)
        args.save_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.info("Saved report JSON to %s", args.save_report)
    if args.send_seatalk:
        LOGGER.info("Sending report to SeaTalk...")
        seatalk_settings = SeaTalkSettings(
            app_id=settings.seatalk_app_id,
            app_secret=settings.seatalk_app_secret,
            group_id=settings.seatalk_group_id,
            employee_code=settings.seatalk_employee_code,
        )
        SeaTalkClient(seatalk_settings).send_text(render_seatalk_report(report, title=args.seatalk_title))
        LOGGER.info("SeaTalk message sent successfully.")


if __name__ == "__main__":
    raise SystemExit(main())
