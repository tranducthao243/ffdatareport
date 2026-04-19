import unittest
from unittest.mock import Mock, patch

from datasocial.formatter import render_seatalk_report
from datasocial.seatalk import SeaTalkClient, SeaTalkSettings
from seatalk.callbacks import build_callback_context, extract_click_value, extract_message_text, parse_click_payload
from seatalk.callback_server import build_runtime
from seatalk.payloads import build_interactive_payload, build_report_interactive_payload
from seatalk.sender import send_report_packages


class DatasocialSeatalkFormatterTests(unittest.TestCase):
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
                    {"label": "Data Campaign", "callbackPayload": '{"action":"campaign"}'},
                ],
            }
        ]

        result = send_report_packages(packages, app_id="id", app_secret="secret")

        client.send_text.assert_called_once()
        client.send_interactive.assert_called_once()
        self.assertEqual(result[0]["status"], "sent")
        self.assertEqual(result[0]["interactiveStatus"], "sent")


if __name__ == "__main__":
    unittest.main()
