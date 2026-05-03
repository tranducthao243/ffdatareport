import unittest
import base64
import json
from datetime import datetime
from unittest.mock import Mock, patch
from PIL import Image

from app.health import classify_private_command, extract_hashtag_query, format_hashtag_report, normalize_command_text
from app.private_reports import build_hashtag_report_data, build_kol_report_data, format_hashtag_report_v2, format_kol_report
from report.renderers import render_topd
from datasocial.formatter import render_seatalk_report
from datasocial.seatalk import SeaTalkClient, SeaTalkSettings
from seatalk.identity import UnifiedUser, build_unified_user, load_env_role_directory
from seatalk.callbacks import (
    build_callback_context,
    extract_click_value,
    extract_message_image_url,
    extract_message_tag,
    extract_message_text,
    parse_click_payload,
)
from seatalk.callback_server import build_runtime
from seatalk.group_thread_service import (
    derive_group_thread_id,
    is_allowed_ctv_group,
    message_addresses_bot,
    normalize_group_thread_command_text,
    split_csv_env,
    strip_group_bot_aliases,
)
from seatalk.private_bot_service import build_private_help_text, build_private_usage_text
from seatalk.interactive import build_interactive_actions, build_interactive_groups
from seatalk.payloads import build_interactive_group_payload, build_interactive_payload, build_report_interactive_payload
from seatalk.sender import send_report_packages
from seatalk.uploadimage import (
    _filename_match_tokens,
    _pick_vendor_row_after_save,
    _pick_new_vendor_url,
    _safe_filename_stem,
    convert_image_to_png,
    get_latest_unprocessed_image_for_user,
    mark_image_processed_for_user,
    store_latest_image_for_user,
)
from app.pipeline import build_store_from_export
from datasocial.exporter import export_rows_to_csv_bytes
import tempfile
from pathlib import Path


class DatasocialSeatalkFormatterTests(unittest.TestCase):
    def test_private_help_and_usage_text_services(self):
        help_text = build_private_help_text("admin")
        usage_text = build_private_usage_text()
        self.assertIn("`kol`", help_text)
        self.assertIn("`upscale`", help_text)
        self.assertNotIn("ducthao.tran@garena.vn", help_text)
        self.assertIn("ducthao.tran@garena.vn", usage_text)

    def test_ctv_group_allowlist_service(self):
        runtime = {"ctv_group_ids": ["group-1", "group-2"]}
        self.assertEqual(split_csv_env("group-1, group-2"), ["group-1", "group-2"])
        self.assertTrue(is_allowed_ctv_group(runtime, {"group_id": "group-1"}))
        self.assertFalse(is_allowed_ctv_group(runtime, {"group_id": "group-x"}))

    def test_group_thread_helpers_follow_seatalk_rules(self):
        context_with_thread = {"thread_id": "thread-1", "message_id": "message-1"}
        context_without_thread = {"thread_id": "", "message_id": "message-2"}
        aliases = ["bot data kols", "bot"]

        self.assertEqual(derive_group_thread_id(context_with_thread), "thread-1")
        self.assertEqual(derive_group_thread_id(context_without_thread), "message-2")
        self.assertTrue(message_addresses_bot("@Bot Data KOLs chart", aliases))
        self.assertFalse(message_addresses_bot("@campaign", aliases))
        self.assertEqual(strip_group_bot_aliases("@Bot Data KOLs chart", aliases), "chart")
        self.assertEqual(
            normalize_group_thread_command_text("@Bot Data KOLs campaign", aliases),
            "campaign",
        )

    def test_hashtag_command_is_detected_with_and_without_space(self):
        self.assertEqual(classify_private_command("hashtag ob53"), "hashtag")
        self.assertEqual(classify_private_command("hashtagob53"), "hashtag")
        self.assertEqual(extract_hashtag_query("hashtag #ob53"), "ob53")
        self.assertEqual(extract_hashtag_query("hashtagob53"), "ob53")

    def test_imagelink_command_alias_is_detected(self):
        self.assertEqual(classify_private_command("imagelink"), "imagelink")
        self.assertEqual(classify_private_command("uploadimage"), "imagelink")
        self.assertEqual(classify_private_command("upscale"), "upscale")
        self.assertEqual(classify_private_command("enhanceimage"), "upscale")
        self.assertEqual(classify_private_command("kol hieu dau da"), "kol")
        self.assertEqual(normalize_command_text("Hiếu Đầu Đà"), "hieu dau da")

    def test_format_hashtag_report_summarizes_views_by_category(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "Dance One",
                "Category": "Trend Dance",
                "__category_id": "119",
                "Post id": "tt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 1 #ob53",
                "Link": "https://www.tiktok.com/@dance/video/1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#ob53",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "500000",
            },
            {
                "ID": "2",
                "Platform": "Youtube",
                "Channel id": "yt-1",
                "Channel name": "Roblox One",
                "Category": "Roblox",
                "__category_id": "368",
                "Post id": "yt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 2 #ob53",
                "Link": "https://www.youtube.com/watch?v=1",
                "Publish time": "2026-04-18 11:00:00",
                "Hashtag": "#ob53",
                "Comment": "5",
                "Duration (second)": "20",
                "Engagement": "40",
                "Reaction": "20",
                "View": "200000",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))
            build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")

            answer = format_hashtag_report(db_path, "hashtagob53")

            self.assertIn("Hashtag: `#ob53`", answer)
            self.assertIn("Tổng view: 700.0K", answer)
            self.assertIn("Khung dữ liệu: `2026-04-17 -> 2026-04-18`", answer)
            self.assertIn("Trend Dance", answer)
            self.assertIn("Roblox", answer)

    def test_format_hashtag_report_v2_lists_top_videos_and_official_share(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "Dance One",
                "Category": "Trend Dance",
                "__category_id": "119",
                "Post id": "tt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 1 #ob53",
                "Link": "https://www.tiktok.com/@dance/video/1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#ob53",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "500000",
            },
            {
                "ID": "2",
                "Platform": "Facebook",
                "Channel id": "fb-1",
                "Channel name": "Official One",
                "Category": "Official",
                "__category_id": "13",
                "Post id": "fb-post-1",
                "Post type": "VIDEO",
                "Post description": "Official #ob53",
                "Link": "https://facebook.com/post/1",
                "Publish time": "2026-04-18 11:00:00",
                "Hashtag": "#ob53",
                "Comment": "5",
                "Duration (second)": "20",
                "Engagement": "40",
                "Reaction": "20",
                "View": "200000",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))
            build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")

            answer = format_hashtag_report_v2(db_path, "hashtag ob53")

            self.assertIn("TOP VIDEO NỔI BẬT (7 NGÀY)", answer)
            self.assertIn("Official contribution:", answer)
            self.assertIn("Percentage:", answer)

    def test_build_hashtag_report_data_builds_30_day_chart(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "KOL One",
                "Category": "Gameplay Creator",
                "__category_id": "14",
                "Post id": "tt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 1 #ob53",
                "Link": "https://www.tiktok.com/@kol/video/1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#ob53",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "500000",
            },
            {
                "ID": "2",
                "Platform": "Facebook",
                "Channel id": "fb-1",
                "Channel name": "Official One",
                "Category": "Official",
                "__category_id": "13",
                "Post id": "fb-post-1",
                "Post type": "VIDEO",
                "Post description": "Official #ob53",
                "Link": "https://facebook.com/post/1",
                "Publish time": "2026-04-18 11:00:00",
                "Hashtag": "#ob53",
                "Comment": "5",
                "Duration (second)": "20",
                "Engagement": "40",
                "Reaction": "20",
                "View": "200000",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))
            build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")

            report_data = build_hashtag_report_data(
                db_path,
                "hashtag ob53",
                now=datetime.fromisoformat("2026-04-18T12:00:00"),
            )

            self.assertTrue(report_data["hasData"])
            self.assertEqual(report_data["totalViews"], 700000)
            self.assertEqual(report_data["totalClips"], 2)
            self.assertEqual(len(report_data["dailyChart"]), 30)
            self.assertEqual(report_data["dailyChart"][-2]["totalViews"], 500000)
            self.assertEqual(report_data["dailyChart"][-1]["totalViews"], 200000)

    def test_build_hashtag_report_data_uses_latest_data_day_when_store_lags(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "KOL One",
                "Category": "Gameplay Creator",
                "__category_id": "14",
                "Post id": "tt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 1 #ob53",
                "Link": "https://www.tiktok.com/@kol/video/1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#ob53",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "500000",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))
            build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")

            report_data = build_hashtag_report_data(
                db_path,
                "hashtag ob53",
                now=datetime.fromisoformat("2026-05-01T12:00:00"),
            )

            self.assertTrue(report_data["hasData"])
            self.assertEqual(len(report_data["dailyChart"]), 30)
            self.assertEqual(report_data["dailyChart"][-1]["date"], "2026-04-17")
            self.assertEqual(report_data["dailyChart"][-1]["totalViews"], 500000)

    def test_format_kol_report_aggregates_channels_from_mapping(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Youtube",
                "Channel id": "yt-1",
                "Channel name": "KOL One YT",
                "Category": "Gameplay Creator",
                "__category_id": "14",
                "Post id": "yt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 1 #freefire",
                "Link": "https://youtube.com/watch?v=1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "500000",
            },
            {
                "ID": "2",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "KOL One TT",
                "Category": "Gameplay Creator",
                "__category_id": "14",
                "Post id": "tt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 2 #ff",
                "Link": "https://tiktok.com/@kol/video/1",
                "Publish time": "2026-04-18 10:00:00",
                "Hashtag": "#ff",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "300000",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            mapping_path = root / "kols.json"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))
            build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")
            mapping_path.write_text(
                json.dumps(
                    {
                        "kols": [
                            {
                                "name": "KOL One",
                                "aliases": ["kolone"],
                                "channels": [
                                    {"platform": "youtube", "channelName": "KOL One YT"},
                                    {"platform": "tiktok", "channelName": "KOL One TT"},
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            answer = format_kol_report(db_path, "kol KOL One", mapping_path=mapping_path)

            self.assertIn("KOL: KOL One", answer)
            self.assertIn("Tổng view:", answer)
            self.assertIn("TOP hashtag:", answer)
            self.assertIn("YouTube: KOL One YT", answer)

    def test_format_kol_report_can_fallback_to_channel_name_without_mapping(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Youtube",
                "Channel id": "yt-1",
                "Channel name": "Hiếu Đầu Đà",
                "Category": "Gameplay Creator",
                "__category_id": "14",
                "Post id": "yt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 1 #freefire",
                "Link": "https://youtube.com/watch?v=1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "500000",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            mapping_path = root / "kols.json"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))
            build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")
            mapping_path.write_text(json.dumps({"kols": []}), encoding="utf-8")

            answer = format_kol_report(db_path, "kol Hiếu Đầu Đà", mapping_path=mapping_path)

            self.assertIn("KOL: Hiếu Đầu Đà", answer)
            self.assertIn("Tổng view:", answer)

    def test_build_kol_report_data_picks_highest_view_channel_for_chart(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Youtube",
                "Channel id": "yt-1",
                "Channel name": "Jeeker YT",
                "Category": "Gameplay Creator",
                "__category_id": "14",
                "Post id": "yt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 1 #freefire",
                "Link": "https://youtube.com/watch?v=1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "200000",
            },
            {
                "ID": "2",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "Jeeker TT",
                "Category": "Gameplay Creator",
                "__category_id": "14",
                "Post id": "tt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 2 #ff",
                "Link": "https://tiktok.com/@jeeker/video/1",
                "Publish time": "2026-04-18 10:00:00",
                "Hashtag": "#ff",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "600000",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            mapping_path = root / "kols.json"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))
            build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")
            mapping_path.write_text(
                json.dumps(
                    {
                        "kols": [
                            {
                                "name": "Jeeker",
                                "aliases": ["jeeker"],
                                "channels": [
                                    {"platform": "youtube", "channelName": "Jeeker YT"},
                                    {"platform": "tiktok", "channelName": "Jeeker TT"},
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report_data = build_kol_report_data(db_path, "kol Jeeker", mapping_path=mapping_path)

            self.assertEqual(report_data["primaryChannel"]["platform"], "tiktok")
            self.assertEqual(report_data["primaryChannel"]["channelName"], "Jeeker TT")
            self.assertEqual(len(report_data["primaryChannelDailyChart"]), 30)

    def test_build_unified_user_resolves_superadmin_by_email(self):
        callback_context = {
            "employee_code": "110677",
            "email": "ducthao.tran@garena.vn",
            "seatalk_id": "9306358918",
        }
        unified = build_unified_user(
            callback_context,
            [UnifiedUser(role="superadmin", employee_code="110677", email="ducthao.tran@garena.vn", seatalk_user_id="9306358918")],
        )
        self.assertEqual(unified["role"], "superadmin")

    @patch.dict(
        "os.environ",
        {
            "SEATALK_ADMIN_EMAILS": "admin@garena.vn",
            "SEATALK_SUPERADMIN_SEATALK_IDS": "9306358918",
        },
        clear=False,
    )
    def test_env_role_directory_allows_single_identifier_match(self):
        env_directory = load_env_role_directory()

        admin_user = build_unified_user(
            {"email": "admin@garena.vn", "employee_code": "", "seatalk_id": ""},
            [],
            env_directory=env_directory,
        )
        superadmin_user = build_unified_user(
            {"email": "", "employee_code": "", "seatalk_id": "9306358918"},
            [],
            env_directory=env_directory,
        )

        self.assertEqual(admin_user["role"], "admin")
        self.assertEqual(superadmin_user["role"], "superadmin")

    def test_render_seatalk_report_legacy_fallback_keeps_summary(self):
        report = {
            "generatedAt": "2026-04-12T07:30:33Z",
            "summary": {
                "totalRowsFetched": 9,
                "totalRowsAfterFilters": 5,
            },
        }

        content = render_seatalk_report(report, title="Daily FFVN")

        self.assertIn("**Daily FFVN**", content)

    def test_render_topd_includes_official_contribution_section(self):
        lines = render_topd(
            {
                "campaigns": [
                    {
                        "campaignName": "OB53",
                        "hashtags": ["ob53"],
                        "totalViews": 1000,
                        "totalClips": 2,
                        "kpiPercent": 10,
                        "kpiTarget": 10000,
                        "daysLeft": 3,
                        "averageViewPerClip": 500,
                        "forecastKpiText": "Dự kiến 20% KPI",
                        "historyCompare": {},
                        "topRecentTikTok": [],
                        "officialContribution": {"totalViews": 200, "totalClips": 1, "percentage": 20},
                        "topKolsWithoutCampaignWindow": {"from": "2026-04-01", "to": "2026-04-07"},
                        "topKolsWithoutCampaign": [],
                    }
                ]
            }
        )
        rendered = "\n".join(lines)
        self.assertIn("**4. Official contribution**", rendered)
        self.assertIn("20%", rendered)

    def test_build_interactive_payload_contains_callback_buttons(self):
        payload = build_interactive_payload(
            title="Bao cao",
            description="Chon du lieu muon xem them.",
            actions=[
                {"label": "Data Campaign", "callbackPayload": '{"action":"campaign"}'},
                {"label": "Official Channel", "callbackPayload": '{"action":"official"}'},
            ],
        )

        self.assertEqual(payload["tag"], "interactive_message")
        elements = payload["interactive_message"]["elements"]
        self.assertEqual(elements[0]["element_type"], "title")
        self.assertEqual(elements[1]["element_type"], "description")
        self.assertEqual(elements[2]["element_type"], "button_group")
        self.assertEqual(elements[0]["title"]["text"], "Bao cao")
        self.assertEqual(elements[1]["description"]["format"], 1)
        self.assertEqual(len(elements[2]["button_group"]), 2)
        self.assertEqual(elements[2]["button_group"][0]["button_type"], "callback")

    def test_build_report_interactive_payload_embeds_rendered_text(self):
        payload = build_report_interactive_payload(
            {
                "title": "Bao cao tong hop",
                "reportCode": "SO1",
                "renderedText": "Bao cao tong hop\nDong 1\nDong 2",
                "interactiveActions": [
                    {"label": "Data Campaign", "callbackPayload": '{"action":"campaign"}'},
                ],
            }
        )

        elements = payload["interactive_message"]["elements"]
        self.assertEqual(elements[0]["title"]["text"], "Bao cao tong hop")
        self.assertEqual(elements[1]["description"]["text"], "Mo nhanh phan du lieu can xem them.")

    def test_build_interactive_groups_split_campaign_and_trend_cards(self):
        package = {
            "reportCode": "SO1",
            "groupName": "main",
            "generatedAt": "2026-04-20T10:00:00",
        }
        package["interactiveActions"] = build_interactive_actions(package)

        groups = build_interactive_groups(package)

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["description"], "")
        self.assertEqual(len(groups[0]["actions"]), 2)
        self.assertEqual(groups[1]["description"], "")
        self.assertEqual(len(groups[1]["actions"]), 2)

        payload = build_interactive_group_payload(groups[0])
        self.assertEqual(payload["interactive_message"]["elements"][0]["element_type"], "button_group")

    def test_parse_click_payload_decodes_json_value(self):
        payload = parse_click_payload('{"action":"open_report","target_report_code":"TOPD_REPORT"}')

        self.assertEqual(payload["action"], "open_report")
        self.assertEqual(payload["target_report_code"], "TOPD_REPORT")

    def test_extract_click_value_reads_nested_action_value(self):
        event = {"action": {"value": '{"action":"open_report"}'}}

        self.assertEqual(extract_click_value(event), '{"action":"open_report"}')

    def test_build_callback_context_collects_thread_metadata(self):
        event = {
            "group_id": "group-1",
            "message_id": "message-1",
            "thread_id": "thread-1",
            "employee_code": "emp-1",
            "email": "tester@example.com",
            "seatalk_id": "seatalk-1",
            "button": {"value": '{"action":"open_report"}'},
        }

        context = build_callback_context(event)

        self.assertEqual(context["group_id"], "group-1")
        self.assertEqual(context["message_id"], "message-1")
        self.assertEqual(context["thread_id"], "thread-1")
        self.assertEqual(context["employee_code"], "emp-1")
        self.assertEqual(context["email"], "tester@example.com")
        self.assertEqual(context["seatalk_id"], "seatalk-1")

    def test_build_callback_context_reads_group_sender_inside_message(self):
        event = {
            "group_id": "group-1",
            "message": {
                "message_id": "message-1",
                "thread_id": "",
                "sender": {
                    "employee_code": "emp-2",
                    "email": "group@example.com",
                    "seatalk_id": "seatalk-2",
                },
                "text": {"plain_text": "@Bot Data KOLs chart"},
            },
        }

        context = build_callback_context(event)

        self.assertEqual(context["employee_code"], "emp-2")
        self.assertEqual(context["email"], "group@example.com")
        self.assertEqual(context["seatalk_id"], "seatalk-2")

    def test_extract_message_text_reads_private_message_plain_text(self):
        event = {"message": {"text": {"plain_text": "health"}}}

        self.assertEqual(extract_message_text(event), "health")

    def test_extract_message_image_url_reads_private_image_event(self):
        event = {
            "message": {
                "tag": "image",
                "image": {"content": "https://openapi.seatalk.io/messaging/v2/file/example"},
            }
        }

        self.assertEqual(extract_message_tag(event), "image")
        self.assertEqual(
            extract_message_image_url(event),
            "https://openapi.seatalk.io/messaging/v2/file/example",
        )

    def test_uploadimage_store_keeps_latest_unprocessed_image_per_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "seatalk_images.json"

            store_latest_image_for_user(
                store_path,
                user_key="private:110677",
                employee_code="110677",
                seatalk_id="9306358918",
                message_id="m1",
                image_url="https://openapi.seatalk.io/messaging/v2/file/m1",
                thread_id="m1",
            )
            store_latest_image_for_user(
                store_path,
                user_key="private:110677",
                employee_code="110677",
                seatalk_id="9306358918",
                message_id="m2",
                image_url="https://openapi.seatalk.io/messaging/v2/file/m2",
                thread_id="m2",
            )

            latest = get_latest_unprocessed_image_for_user(
                store_path,
                user_key="private:110677",
                command_name="uploadimage",
            )

            self.assertIsNotNone(latest)
            self.assertEqual(latest["message_id"], "m2")
            self.assertFalse(latest["processed"])

            mark_image_processed_for_user(
                store_path,
                user_key="private:110677",
                message_id="m2",
                command_name="uploadimage",
            )
            self.assertIsNone(
                get_latest_unprocessed_image_for_user(
                    store_path,
                    user_key="private:110677",
                    command_name="uploadimage",
                )
            )
            self.assertIsNotNone(
                get_latest_unprocessed_image_for_user(
                    store_path,
                    user_key="private:110677",
                    command_name="removebg",
                )
            )

    def test_mark_processed_does_not_consume_newer_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "seatalk_images.json"

            store_latest_image_for_user(
                store_path,
                user_key="private:110677",
                employee_code="110677",
                seatalk_id="9306358918",
                message_id="old-msg",
                image_url="https://openapi.seatalk.io/messaging/v2/file/old",
                thread_id="old-msg",
            )
            store_latest_image_for_user(
                store_path,
                user_key="private:110677",
                employee_code="110677",
                seatalk_id="9306358918",
                message_id="new-msg",
                image_url="https://openapi.seatalk.io/messaging/v2/file/new",
                thread_id="new-msg",
            )

            mark_image_processed_for_user(
                store_path,
                user_key="private:110677",
                message_id="old-msg",
                command_name="uploadimage",
            )

            latest = get_latest_unprocessed_image_for_user(
                store_path,
                user_key="private:110677",
                command_name="uploadimage",
            )
            self.assertIsNotNone(latest)
            self.assertEqual(latest["message_id"], "new-msg")

    def test_group_image_store_can_use_group_actor_key_without_employee_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "seatalk_images.json"

            store_latest_image_for_user(
                store_path,
                user_key="group:group-1:actor:seatalk-1",
                employee_code="",
                seatalk_id="seatalk-1",
                message_id="group-msg-1",
                image_url="https://openapi.seatalk.io/messaging/v2/file/group-msg-1",
                thread_id="thread-1",
            )

            latest = get_latest_unprocessed_image_for_user(
                store_path,
                user_key="group:group-1:actor:seatalk-1",
                command_name="uploadimage",
            )

            self.assertIsNotNone(latest)
            self.assertEqual(latest["seatalk_id"], "seatalk-1")
            self.assertEqual(latest["message_id"], "group-msg-1")

    def test_uploadimage_filename_tokens_use_unique_hash_suffix(self):
        stem_one = _safe_filename_stem("u7YirumAclDz6kjP41NhyMkXvXNAhNTqCAnQvTUQ9YuCzzoUoFE7bJ5O")
        stem_two = _safe_filename_stem("u7YirumAclDz6kjP41NhyMk5vXNAhNTqCAkhGig01ZHLFKK7Ns21ug0K")

        self.assertNotEqual(stem_one, stem_two)
        self.assertNotEqual(stem_one.rsplit("-", 1)[-1], stem_two.rsplit("-", 1)[-1])
        self.assertIn(stem_one.rsplit("-", 1)[-1], _filename_match_tokens(Path(f"{stem_one}.jpg")))

    def test_pick_new_vendor_url_prefers_newest_and_owner_email(self):
        rows = [
            {
                "id": "1",
                "email": "other@example.com",
                "file": "https://files.garena.vn/garena-social/public/2026/4/22/old.png",
                "createdAt": "2026-04-22T08:30:00.000Z",
            },
            {
                "id": "2",
                "email": "owner@example.com",
                "file": "https://files.garena.vn/garena-social/public/2026/4/22/new-owner.png",
                "createdAt": "2026-04-22T08:45:00.000Z",
            },
            {
                "id": "3",
                "email": "owner@example.com",
                "file": "https://files.garena.vn/garena-social/public/2026/4/22/newer-owner.png",
                "createdAt": "2026-04-22T08:46:00.000Z",
            },
        ]
        selected = _pick_new_vendor_url(
            rows,
            before_urls={"https://files.garena.vn/garena-social/public/2026/4/22/old.png"},
            public_url_prefix="https://files.garena.vn/garena-social/public/",
            owner_email="owner@example.com",
        )
        self.assertEqual(selected, "https://files.garena.vn/garena-social/public/2026/4/22/newer-owner.png")

    def test_pick_vendor_row_after_save_prefers_filename_match_and_rejects_wrong_path(self):
        rows = [
            {
                "id": "1",
                "email": "owner@example.com",
                "file": "https://files.garena.vn/garena-vendor-system/public/2026/4/22/seatalk-110677-1776876049.1t2bq448fx.png",
                "createdAt": "2026-04-22T16:41:00.614Z",
            },
            {
                "id": "2",
                "email": "owner@example.com",
                "file": "https://files.garena.vn/garena-social/public/2026/4/22/older.png",
                "createdAt": "2026-04-22T16:39:00.614Z",
            },
        ]

        selected, source, filename_matches, candidate_new_urls = _pick_vendor_row_after_save(
            rows,
            before_urls={"https://files.garena.vn/garena-social/public/2026/4/22/older.png"},
            public_url_prefix="https://files.garena.vn/garena-social/public/",
            owner_email="owner@example.com",
            uploaded_filename_token="seatalk-110677-1776876049",
        )

        self.assertEqual(selected, "")
        self.assertEqual(source, "filename_match_wrong_path")
        self.assertEqual(len(filename_matches), 1)
        self.assertEqual(candidate_new_urls, [])

    def test_convert_image_to_png_rewrites_webp_output_for_seatalk(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "result.webp"
            Image.new("RGBA", (4, 4), (255, 0, 0, 128)).save(source_path, format="WEBP")

            converted_path = convert_image_to_png(source_path)

            self.assertEqual(converted_path.suffix.lower(), ".png")
            self.assertTrue(converted_path.exists())

    def test_callback_server_build_runtime_reads_preset_data(self):
        class Args:
            db_path = "outputs/ffvn_master.sqlite"
            groups_config = "config/groups.json"
            reports_config = "config/reports.json"
            campaigns_config = "config/campaigns.json"
            preset = "ffvn_master_daily"
            report_mode = "today_so_far"
            report_timezone = "Asia/Ho_Chi_Minh"
            repo = "tranducthao243/ffdatareport"
            artifact_name = "ffvn-daily-fetch-latest"
            artifact_token = ""
            sync_on_start = False
            sync_on_click = False
            verify_signature = False
            signing_secret = ""

        with patch.dict(
            "os.environ",
            {
                "SEATALK_ADMIN_EMPLOYEE_CODES": "e_1,e_2",
                "SEATALK_ADMIN_EMAILS": "a@example.com,b@example.com",
                "SEATALK_ADMIN_SEATALK_IDS": "1001,1002",
            },
            clear=False,
        ):
            runtime = build_runtime(Args())

        self.assertIn(13, runtime["preset_category_ids"])
        self.assertIn(1, runtime["preset_platform_ids"])
        env_roles = runtime["env_role_directory"]
        self.assertTrue(any(item.role == "admin" and item.employee_code == "e_1" for item in env_roles))
        self.assertTrue(any(item.role == "admin" and item.email == "a@example.com" for item in env_roles))
        self.assertTrue(any(item.role == "admin" and item.seatalk_user_id == "1001" for item in env_roles))

    def test_callback_server_build_runtime_includes_ctv_kol_group_in_allowlist(self):
        class Args:
            db_path = "outputs/ffvn_master.sqlite"
            groups_config = "config/groups.json"
            reports_config = "config/reports.json"
            campaigns_config = "config/campaigns.json"
            preset = "ffvn_master_daily"
            report_mode = "today_so_far"
            report_timezone = "Asia/Ho_Chi_Minh"
            repo = "tranducthao243/ffdatareport"
            artifact_name = "ffvn-daily-fetch-latest"
            artifact_token = ""
            sync_on_start = False
            sync_on_click = False
            verify_signature = False
            signing_secret = ""

        with patch.dict(
            "os.environ",
            {
                "SEATALK_CTV_GROUP_IDS": "group-1,group-2",
                "SEATALK_CTV_KOL_GROUP_ID": "group-3",
            },
            clear=False,
        ):
            runtime = build_runtime(Args())

        self.assertEqual(runtime["ctv_group_ids"], ["group-1", "group-2", "group-3"])

    def test_group_send_includes_thread_fields_when_present(self):
        client = SeaTalkClient(
            SeaTalkSettings(
                app_id="app",
                app_secret="secret",
                group_id="group-1",
                thread_id="thread-1",
                quoted_message_id="message-1",
            )
        )
        client.token = "token"
        response = Mock()
        response.ok = True
        response.json.return_value = {"code": 0}
        client.session.post = Mock(return_value=response)

        client.send_text("hello")

        _, kwargs = client.session.post.call_args
        self.assertEqual(kwargs["json"]["group_id"], "group-1")
        self.assertEqual(kwargs["json"]["message"]["thread_id"], "thread-1")
        self.assertNotIn("thread_id", kwargs["json"])
        self.assertNotIn("quoted_message_id", kwargs["json"])

    def test_group_typing_includes_thread_id_when_present(self):
        client = SeaTalkClient(
            SeaTalkSettings(
                app_id="app",
                app_secret="secret",
                group_id="group-1",
                thread_id="thread-1",
            )
        )
        client.token = "token"
        response = Mock()
        response.ok = True
        response.json.return_value = {"code": 0}
        client.session.post = Mock(return_value=response)

        client.set_typing_status()

        args, kwargs = client.session.post.call_args
        self.assertTrue(args[0].endswith("/messaging/v2/group_chat_typing"))
        self.assertEqual(kwargs["json"]["group_id"], "group-1")
        self.assertEqual(kwargs["json"]["thread_id"], "thread-1")

    def test_private_typing_includes_employee_code(self):
        client = SeaTalkClient(
            SeaTalkSettings(
                app_id="app",
                app_secret="secret",
                employee_code="e_123",
                thread_id="message-1",
            )
        )
        client.token = "token"
        response = Mock()
        response.ok = True
        response.json.return_value = {"code": 0}
        client.session.post = Mock(return_value=response)

        client.set_typing_status()

        args, kwargs = client.session.post.call_args
        self.assertTrue(args[0].endswith("/messaging/v2/single_chat_typing"))
        self.assertEqual(kwargs["json"]["employee_code"], "e_123")
        self.assertEqual(kwargs["json"]["thread_id"], "message-1")

    def test_send_image_bytes_uses_image_content_message(self):
        client = SeaTalkClient(
            SeaTalkSettings(
                app_id="app",
                app_secret="secret",
                employee_code="e_123",
                thread_id="thread-1",
                quoted_message_id="message-1",
            )
        )
        client.token = "token"
        response = Mock()
        response.ok = True
        response.json.return_value = {"code": 0}
        client.session.post = Mock(return_value=response)

        client.send_image_bytes(b"png-bytes")

        _, kwargs = client.session.post.call_args
        self.assertEqual(kwargs["json"]["message"]["tag"], "image")
        self.assertEqual(kwargs["json"]["thread_id"], "thread-1")
        self.assertEqual(kwargs["json"]["quoted_message_id"], "message-1")
        content = kwargs["json"]["message"]["image"]["content"]
        self.assertEqual(base64.b64decode(content.encode("ascii")), b"png-bytes")

    def test_send_image_url_uses_image_content_message(self):
        client = SeaTalkClient(
            SeaTalkSettings(
                app_id="app",
                app_secret="secret",
                employee_code="e_123",
                thread_id="thread-1",
            )
        )
        client.token = "token"
        response = Mock()
        response.ok = True
        response.json.return_value = {"code": 0}
        client.session.post = Mock(return_value=response)

        client.send_image_url("https://files.example.com/image.png")

        _, kwargs = client.session.post.call_args
        self.assertEqual(kwargs["json"]["message"]["tag"], "image")
        self.assertEqual(kwargs["json"]["message"]["image"]["content"], "https://files.example.com/image.png")
        self.assertEqual(kwargs["json"]["thread_id"], "thread-1")

    @patch("seatalk.sender.build_seatalk_client")
    def test_send_report_packages_sends_text_then_interactive_when_actions_exist(self, mock_build_client):
        client = Mock()
        mock_build_client.return_value = client
        packages = [
            {
                "groupName": "main",
                "reportCode": "SO1",
                "resolvedGroupId": "group-1",
                "renderedText": "Bao cao\nhello",
                "title": "Bao cao",
                "interactiveActions": [
                    {"label": "Data Campaign", "callbackPayload": '{"action":"campaign"}', "actionGroup": "campaign_official"},
                    {"label": "Official Channel", "callbackPayload": '{"action":"official"}', "actionGroup": "campaign_official"},
                    {"label": "Trend nhảy", "callbackPayload": '{"action":"trend_dance"}', "actionGroup": "trend"},
                    {"label": "Trend tình huống", "callbackPayload": '{"action":"trend_situation"}', "actionGroup": "trend"},
                ],
            }
        ]

        result = send_report_packages(packages, app_id="id", app_secret="secret")

        client.send_text.assert_called_once()
        self.assertEqual(client.send_interactive.call_count, 2)
        self.assertEqual(result[0]["status"], "sent")
        self.assertEqual(result[0]["interactiveStatus"], "sent")

    @patch("seatalk.sender.build_seatalk_client")
    def test_send_report_packages_sends_chart_when_present(self, mock_build_client):
        client = Mock()
        mock_build_client.return_value = client
        with tempfile.TemporaryDirectory() as tmp:
            chart_path = Path(tmp) / "chart.png"
            Image.new("RGB", (10, 10), (255, 255, 255)).save(chart_path, format="PNG")
            packages = [
                {
                    "groupName": "main",
                    "reportCode": "SO1",
                    "resolvedGroupId": "group-1",
                    "renderedText": "Bao cao\nhello",
                    "title": "Bao cao",
                    "chartPath": str(chart_path),
                    "interactiveActions": [],
                }
            ]

            result = send_report_packages(packages, app_id="id", app_secret="secret")

            client.send_image_path.assert_called_once()
            self.assertEqual(result[0]["chartStatus"], "sent")


if __name__ == "__main__":
    unittest.main()
