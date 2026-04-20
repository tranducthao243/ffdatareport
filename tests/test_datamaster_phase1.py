import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.health import format_health_alert
from app.pipeline import build_configured_reports, build_store_from_export
from datasocial.exceptions import DatasocialError
from datasocial.exporter import export_rows_to_csv_bytes


class DataMasterPhase1Tests(unittest.TestCase):
    def test_build_store_and_configured_reports(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "KOL TikTok 1",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "tt-post-1",
                "Post type": "VIDEO",
                "Post description": "TikTok A #freefire",
                "Link": "https://www.tiktok.com/@tt/video/1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#freefire #garena",
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
                "Channel name": "KOL YouTube 1",
                "Category": "Giải trí_Creator",
                "__category_id": "22",
                "Post id": "yt-post-1",
                "Post type": "VIDEO",
                "Post description": "YouTube A #ff",
                "Link": "https://www.youtube.com/shorts/1",
                "Publish time": "2026-04-16 11:00:00",
                "Hashtag": "#ff",
                "Comment": "5",
                "Duration (second)": "20",
                "Engagement": "40",
                "Reaction": "20",
                "View": "200000",
            },
            {
                "ID": "3",
                "Platform": "Facebook",
                "Channel id": "fb-off-1",
                "Channel name": "Official FB",
                "Category": "Official",
                "__category_id": "13",
                "Post id": "fb-post-1",
                "Post type": "VIDEO",
                "Post description": "Official FB clip",
                "Link": "https://facebook.com/video/1",
                "Publish time": "2026-04-17 12:00:00",
                "Hashtag": "#freefire",
                "Comment": "1",
                "Duration (second)": "20",
                "Engagement": "10",
                "Reaction": "8",
                "View": "80000",
            },
            {
                "ID": "4",
                "Platform": "Tiktok",
                "Channel id": "tt-camp-1",
                "Channel name": "Campaign TT",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "camp-post-1",
                "Post type": "VIDEO",
                "Post description": "Campaign clip #ob53",
                "Link": "https://www.tiktok.com/@camp/video/1",
                "Publish time": "2026-04-17 09:30:00",
                "Hashtag": "#ob53 #giaitriob53",
                "Comment": "3",
                "Duration (second)": "25",
                "Engagement": "50",
                "Reaction": "30",
                "View": "300000",
            },
            {
                "ID": "5",
                "Platform": "Tiktok",
                "Channel id": "tt-camp-1",
                "Channel name": "Campaign TT",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "camp-post-1",
                "Post type": "VIDEO",
                "Post description": "Campaign clip duplicated #ob53",
                "Link": "https://www.tiktok.com/@camp/video/1",
                "Publish time": "2026-04-17 09:30:00",
                "Hashtag": "#ob53 #giaitriob53",
                "Comment": "3",
                "Duration (second)": "25",
                "Engagement": "50",
                "Reaction": "30",
                "View": "300000",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))

            summary = build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")
            self.assertEqual(summary["postCount"], 4)

            groups_path = root / "groups.json"
            reports_path = root / "reports.json"
            campaigns_path = root / "campaigns.json"
            groups_path.write_text(
                json.dumps(
                    {
                        "groups": [
                            {"name": "main", "enabled": True, "report_code": "SO1", "group_id": "g-main"},
                            {
                                "name": "campaign",
                                "enabled": True,
                                "report_code": "TOPD_REPORT",
                                "group_id": "g-camp",
                                "campaign_names": ["OB53"],
                            },
                            {"name": "official", "enabled": True, "report_code": "TOPF_REPORT", "group_id": "g-off"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            reports_path.write_text(
                json.dumps(
                    {
                        "reports": {
                            "SO1": {"sections": ["TOPA", "TOPB", "TOPC", "TOPE"]},
                            "TOPD_REPORT": {"sections": ["TOPD"]},
                            "TOPF_REPORT": {"sections": ["TOPF"]},
                        }
                    }
                ),
                encoding="utf-8",
            )
            campaigns_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "OB53",
                            "hashtags": ["ob53", "giaitriob53"],
                            "kpi_view_target": 1000000,
                            "start_date": "2026-04-15",
                            "end_date": "2026-04-30",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            history_dir = root / "history"
            history_dir.mkdir(parents=True, exist_ok=True)
            (history_dir / "previous_day.json").write_text(
                json.dumps(
                    {
                        "snapshotDate": "2026-04-17",
                        "reports": {
                            "SO1": {
                                "sections": {
                                    "TOPE": {"totalViews": 700000, "totalClips": 2},
                                }
                            },
                            "TOPD_REPORT": {
                                "sections": {
                                    "TOPD": {
                                        "campaigns": [
                                            {
                                                "campaignName": "OB53",
                                                "totalViews": 200000,
                                                "totalClips": 1,
                                            }
                                        ]
                                    }
                                }
                            },
                            "TOPF_REPORT": {
                                "sections": {
                                    "TOPF": {
                                        "platformTotals": {
                                            "facebook": {"totalViews": 50000, "totalClips": 1},
                                            "tiktok": {"totalViews": 0, "totalClips": 0},
                                            "youtube": {"totalViews": 0, "totalClips": 0},
                                        }
                                    }
                                }
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            payload = build_configured_reports(
                db_path,
                groups_path=groups_path,
                reports_path=reports_path,
                campaigns_path=campaigns_path,
                timezone_name="Asia/Ho_Chi_Minh",
                mode="complete_previous_day",
                source_scope={"category_ids": [13, 14, 22], "platform_ids": [0, 1, 2]},
                now=datetime(2026, 4, 18, 9, 0, 0),
                send=False,
                history_dir=history_dir,
            )

            self.assertEqual(payload["packageCount"], 3)
            self.assertEqual(payload["validation"]["errorCount"], 0)
            self.assertEqual(payload["validation"]["warningCount"], 0)
            self.assertEqual(payload["summary"]["packagesBuilt"], 3)
            main_package = next(item for item in payload["packages"] if item["groupName"] == "main")
            self.assertEqual(main_package["reportCode"], "SO1")
            self.assertEqual(len(main_package["interactiveActions"]), 4)
            topa = next(item for item in main_package["sections"] if item["code"] == "TOPA")
            self.assertEqual(topa["tiktok"][0]["view"], 500000)
            tope = next(item for item in main_package["sections"] if item["code"] == "TOPE")
            self.assertEqual(tope["totalViews"], 1000000)
            self.assertEqual(tope["totalClips"], 3)
            self.assertIn("historyCompare", tope)
            self.assertNotIn("Interactive actions", main_package["renderedText"])

            campaign_package = next(item for item in payload["packages"] if item["groupName"] == "campaign")
            self.assertEqual(campaign_package["interactiveActions"], [])
            topd = next(item for item in campaign_package["sections"] if item["code"] == "TOPD")
            self.assertEqual(topd["campaigns"][0]["totalViews"], 300000)
            self.assertEqual(topd["campaigns"][0]["totalClips"], 1)
            self.assertIn("historyCompare", topd["campaigns"][0])
            self.assertEqual(topd["campaigns"][0]["topKolsWithoutCampaign"][0]["channelName"], "KOL TikTok 1")
            self.assertEqual(topd["campaigns"][0]["topKolsWithoutCampaign"][1]["channelName"], "KOL YouTube 1")

            official_package = next(item for item in payload["packages"] if item["groupName"] == "official")
            self.assertEqual(official_package["interactiveActions"], [])
            topf = next(item for item in official_package["sections"] if item["code"] == "TOPF")
            self.assertEqual(topf["platformTotals"]["facebook"]["totalViews"], 80000)
            self.assertIn("historyCompare", topf)

    def test_invalid_config_fails_with_clear_message(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "KOL TikTok 1",
                "__category_id": "14",
                "Category": "Gameplay_Creator",
                "Post id": "tt-post-1",
                "Post type": "VIDEO",
                "Post description": "TikTok A #freefire",
                "Link": "https://www.tiktok.com/@tt/video/1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "500000",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))
            build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")

            groups_path = root / "groups.json"
            reports_path = root / "reports.json"
            campaigns_path = root / "campaigns.json"
            groups_path.write_text(
                json.dumps(
                    {
                        "groups": [
                            {
                                "name": "campaign",
                                "enabled": True,
                                "report_code": "TOPD_REPORT",
                                "group_id": "g-camp",
                                "campaign_names": ["MISSING_CAMPAIGN"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            reports_path.write_text(
                json.dumps(
                    {
                        "reports": {
                            "TOPD_REPORT": {"sections": ["TOPD"]},
                        }
                    }
                ),
                encoding="utf-8",
            )
            campaigns_path.write_text("[]", encoding="utf-8")

            with self.assertRaises(DatasocialError) as ctx:
                build_configured_reports(
                    db_path,
                    groups_path=groups_path,
                    reports_path=reports_path,
                    campaigns_path=campaigns_path,
                    timezone_name="Asia/Ho_Chi_Minh",
                    mode="complete_previous_day",
                    source_scope={"category_ids": [14], "platform_ids": [0, 2]},
                    now=datetime(2026, 4, 18, 9, 0, 0),
                    send=False,
                )

            self.assertIn("missing campaigns", str(ctx.exception))

    def test_topf_group_is_blocked_when_official_source_not_in_scope(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "KOL TikTok 1",
                "__category_id": "14",
                "Category": "Gameplay_Creator",
                "Post id": "tt-post-1",
                "Post type": "VIDEO",
                "Post description": "TikTok A #freefire",
                "Link": "https://www.tiktok.com/@tt/video/1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "500000",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))
            build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")

            groups_path = root / "groups.json"
            reports_path = root / "reports.json"
            campaigns_path = root / "campaigns.json"
            groups_path.write_text(
                json.dumps(
                    {
                        "groups": [
                            {"name": "main", "enabled": True, "report_code": "SO1", "group_id": "g-main"},
                            {"name": "official", "enabled": True, "report_code": "TOPF_REPORT", "group_id": "g-off"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            reports_path.write_text(
                json.dumps(
                    {
                        "reports": {
                            "SO1": {"sections": ["TOPA", "TOPB", "TOPC", "TOPE"]},
                            "TOPF_REPORT": {"sections": ["TOPF"]},
                        }
                    }
                ),
                encoding="utf-8",
            )
            campaigns_path.write_text("[]", encoding="utf-8")

            payload = build_configured_reports(
                db_path,
                groups_path=groups_path,
                reports_path=reports_path,
                campaigns_path=campaigns_path,
                timezone_name="Asia/Ho_Chi_Minh",
                mode="complete_previous_day",
                source_scope={"category_ids": [14, 22, 23, 24], "platform_ids": [0, 2]},
                now=datetime(2026, 4, 18, 9, 0, 0),
                send=False,
            )

            self.assertEqual(payload["packageCount"], 1)
            self.assertEqual(payload["summary"]["blocked"], 1)
            self.assertEqual(payload["validation"]["warningCount"], 1)
            official_state = next(item for item in payload["validation"]["groupStates"] if item["groupName"] == "official")
            self.assertEqual(official_state["status"], "blocked")

    def test_send_is_blocked_and_admin_alert_prepared_when_official_data_missing(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "KOL TikTok 1",
                "__category_id": "14",
                "Category": "Gameplay_Creator",
                "Post id": "tt-post-1",
                "Post type": "VIDEO",
                "Post description": "TikTok A #freefire",
                "Link": "https://www.tiktok.com/@tt/video/1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "500000",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))
            build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")

            groups_path = root / "groups.json"
            reports_path = root / "reports.json"
            campaigns_path = root / "campaigns.json"
            groups_path.write_text(
                json.dumps(
                    {
                        "groups": [
                            {"name": "main", "enabled": True, "report_code": "SO1", "group_id": "g-main"},
                            {"name": "official", "enabled": True, "report_code": "TOPF_REPORT", "group_id": "g-off"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            reports_path.write_text(
                json.dumps(
                    {
                        "reports": {
                            "SO1": {"sections": ["TOPA", "TOPB", "TOPC", "TOPE"]},
                            "TOPF_REPORT": {"sections": ["TOPF"]},
                        }
                    }
                ),
                encoding="utf-8",
            )
            campaigns_path.write_text("[]", encoding="utf-8")

            payload = build_configured_reports(
                db_path,
                groups_path=groups_path,
                reports_path=reports_path,
                campaigns_path=campaigns_path,
                timezone_name="Asia/Ho_Chi_Minh",
                mode="complete_previous_day",
                source_scope={"category_ids": [13, 14, 22, 23, 24], "platform_ids": [0, 1, 2]},
                now=datetime(2026, 4, 18, 9, 0, 0),
                send=False,
            )

            self.assertTrue(payload["dataHealth"]["blockSend"])
            issue_codes = {item["code"] for item in payload["dataHealth"]["issues"]}
            self.assertIn("official_missing_data", issue_codes)
            alert_text = format_health_alert(payload["dataHealth"])
            self.assertIn("**Canh bao du lieu FFVN**", alert_text)
            self.assertIn("**Nghiem trong**", alert_text)
            self.assertIn("Official mat data", alert_text)


if __name__ == "__main__":
    unittest.main()
