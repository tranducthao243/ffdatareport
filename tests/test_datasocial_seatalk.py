import unittest
from unittest.mock import Mock, patch

from datasocial.formatter import render_seatalk_report
from seatalk.callbacks import extract_click_value, parse_click_payload
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
        self.assertEqual(elements[1]["description"]["text"], "Chon du lieu muon xem them.")

    def test_parse_click_payload_decodes_json_value(self):
        payload = parse_click_payload('{"action":"open_report","target_report_code":"TOPD_REPORT"}')

        self.assertEqual(payload["action"], "open_report")
        self.assertEqual(payload["target_report_code"], "TOPD_REPORT")

    def test_extract_click_value_reads_nested_action_value(self):
        event = {"action": {"value": '{"action":"open_report"}'}}

        self.assertEqual(extract_click_value(event), '{"action":"open_report"}')

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
