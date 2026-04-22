import unittest
import base64
from unittest.mock import Mock, patch
from PIL import Image

from app.health import classify_private_command, extract_hashtag_query, format_hashtag_report
from datasocial.formatter import render_seatalk_report
from datasocial.seatalk import SeaTalkClient, SeaTalkSettings
from seatalk.callbacks import (
    build_callback_context,
    extract_click_value,
    extract_message_image_url,
    extract_message_tag,
    extract_message_text,
    parse_click_payload,
)
from seatalk.callback_server import build_runtime
from seatalk.interactive import build_interactive_actions, build_interactive_groups
from seatalk.payloads import build_interactive_group_payload, build_interactive_payload, build_report_interactive_payload
from seatalk.sender import send_report_packages
from seatalk.uploadimage import (
    _filename_match_tokens,
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
    def test_hashtag_command_is_detected_with_and_without_space(self):
        self.assertEqual(classify_private_command("hashtag ob53"), "hashtag")
        self.assertEqual(classify_private_command("hashtagob53"), "hashtag")
        self.assertEqual(extract_hashtag_query("hashtag #ob53"), "ob53")
        self.assertEqual(extract_hashtag_query("hashtagob53"), "ob53")

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
        self.assertIn("fetched=9", content)
        self.assertIn("after_filter=5", content)

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
        self.assertIn("Campaign", groups[0]["description"])
        self.assertEqual(len(groups[0]["actions"]), 2)
        self.assertIn("Trend", groups[1]["description"])
        self.assertEqual(len(groups[1]["actions"]), 2)

        payload = build_interactive_group_payload(groups[0])
        self.assertEqual(payload["interactive_message"]["elements"][0]["element_type"], "description")

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
                employee_code="110677",
                seatalk_id="9306358918",
                message_id="m1",
                image_url="https://openapi.seatalk.io/messaging/v2/file/m1",
                thread_id="m1",
            )
            store_latest_image_for_user(
                store_path,
                employee_code="110677",
                seatalk_id="9306358918",
                message_id="m2",
                image_url="https://openapi.seatalk.io/messaging/v2/file/m2",
                thread_id="m2",
            )

            latest = get_latest_unprocessed_image_for_user(
                store_path,
                employee_code="110677",
                command_name="uploadimage",
            )

            self.assertIsNotNone(latest)
            self.assertEqual(latest["message_id"], "m2")
            self.assertFalse(latest["processed"])

            mark_image_processed_for_user(
                store_path,
                employee_code="110677",
                message_id="m2",
                command_name="uploadimage",
            )
            self.assertIsNone(
                get_latest_unprocessed_image_for_user(
                    store_path,
                    employee_code="110677",
                    command_name="uploadimage",
                )
            )
            self.assertIsNotNone(
                get_latest_unprocessed_image_for_user(
                    store_path,
                    employee_code="110677",
                    command_name="removebg",
                )
            )

    def test_mark_processed_does_not_consume_newer_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "seatalk_images.json"

            store_latest_image_for_user(
                store_path,
                employee_code="110677",
                seatalk_id="9306358918",
                message_id="old-msg",
                image_url="https://openapi.seatalk.io/messaging/v2/file/old",
                thread_id="old-msg",
            )
            store_latest_image_for_user(
                store_path,
                employee_code="110677",
                seatalk_id="9306358918",
                message_id="new-msg",
                image_url="https://openapi.seatalk.io/messaging/v2/file/new",
                thread_id="new-msg",
            )

            mark_image_processed_for_user(
                store_path,
                employee_code="110677",
                message_id="old-msg",
                command_name="uploadimage",
            )

            latest = get_latest_unprocessed_image_for_user(
                store_path,
                employee_code="110677",
                command_name="uploadimage",
            )
            self.assertIsNotNone(latest)
            self.assertEqual(latest["message_id"], "new-msg")

    def test_uploadimage_filename_tokens_use_unique_hash_suffix(self):
        stem_one = _safe_filename_stem("u7YirumAclDz6kjP41NhyMkXvXNAhNTqCAnQvTUQ9YuCzzoUoFE7bJ5O")
        stem_two = _safe_filename_stem("u7YirumAclDz6kjP41NhyMk5vXNAhNTqCAkhGig01ZHLFKK7Ns21ug0K")

        self.assertNotEqual(stem_one, stem_two)
        self.assertNotEqual(stem_one.rsplit("-", 1)[-1], stem_two.rsplit("-", 1)[-1])
        self.assertIn(stem_one.rsplit("-", 1)[-1], _filename_match_tokens(Path(f"{stem_one}.jpg")))

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
        self.assertEqual(runtime["admin_employee_codes"], ["e_1", "e_2"])
        self.assertEqual(runtime["admin_emails"], ["a@example.com", "b@example.com"])
        self.assertEqual(runtime["admin_seatalk_ids"], ["1001", "1002"])

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
        self.assertEqual(kwargs["json"]["thread_id"], "thread-1")
        self.assertEqual(kwargs["json"]["quoted_message_id"], "message-1")

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


if __name__ == "__main__":
    unittest.main()
