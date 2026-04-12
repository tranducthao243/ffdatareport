import unittest
from datetime import datetime

from datasocial.exporter import (
    build_daily_windows,
    build_export_filter,
    build_export_report,
    dedupe_export_rows,
    export_rows_to_csv_bytes,
    parse_export_csv,
)
from datasocial.formatter import render_seatalk_report
from datasocial.timewindows import build_date_window


class DatasocialExporterTests(unittest.TestCase):
    def test_build_export_filter_matches_web_shape(self):
        export_filter = build_export_filter(
            created_at_gte="2026-04-01",
            created_at_lte="2026-04-12",
            category_ids=[14, 22],
            platform_ids=[0, 2],
            channel_ids=[437],
            metric_ids=[2, 61],
            metric_duration=30,
        )

        self.assertEqual(export_filter["channel"]["categoryId_in"], [14, 22])
        self.assertEqual(export_filter["channel"]["plat_in"], [0, 2])
        self.assertEqual(export_filter["channel"]["id_in"], [437])
        self.assertEqual(export_filter["metricId_in"], [2, 61])

    def test_build_date_window_supports_complete_previous_day(self):
        window = build_date_window(
            "7D",
            mode="complete_previous_day",
            timezone_name="Asia/Ho_Chi_Minh",
            now=datetime(2026, 4, 12, 9, 0, 0),
        )
        self.assertEqual(window.start_date, "2026-04-05")
        self.assertEqual(window.end_date, "2026-04-11")

    def test_build_modular_report_sections(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "Channel TT A",
                "Category": "Gameplay_Creator",
                "Post id": "post-1",
                "Post type": "VIDEO",
                "Post description": "TT 1",
                "Link": "https://www.tiktok.com/@tta/video/111111",
                "Publish time": "2026-04-11 09:00:00",
                "Hashtag": "#freefire #ob53",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "100",
                "Reaction": "90",
                "View": "500000",
            },
            {
                "ID": "2",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "Channel TT A",
                "Category": "Gameplay_Creator",
                "Post id": "post-2",
                "Post type": "VIDEO",
                "Post description": "TT 2",
                "Link": "https://www.tiktok.com/@tta/video/222222",
                "Publish time": "2026-04-10 09:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "100",
                "Reaction": "90",
                "View": "100000",
            },
            {
                "ID": "5",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "Channel TT A",
                "Category": "Gameplay_Creator",
                "Post id": "post-5",
                "Post type": "VIDEO",
                "Post description": "TT 3",
                "Link": "https://www.tiktok.com/@tta/video/555555",
                "Publish time": "2026-04-09 08:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "100",
                "Reaction": "90",
                "View": "120000",
            },
            {
                "ID": "3",
                "Platform": "Youtube",
                "Channel id": "yt-1",
                "Channel name": "Channel YT A",
                "Category": "Giải trí_Creator",
                "Post id": "post-3",
                "Post type": "VIDEO",
                "Post description": "YT 1",
                "Link": "https://www.youtube.com/shorts/abcdef",
                "Publish time": "2026-04-11 10:00:00",
                "Hashtag": "#nhasangtaofreefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "100",
                "Reaction": "90",
                "View": "700000",
            },
            {
                "ID": "4",
                "Platform": "Youtube",
                "Channel id": "yt-1",
                "Channel name": "Channel YT A",
                "Category": "Giải trí_Creator",
                "Post id": "post-4",
                "Post type": "VIDEO",
                "Post description": "YT 2",
                "Link": "https://www.youtube.com/shorts/bbcdef",
                "Publish time": "2026-04-09 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "100",
                "Reaction": "90",
                "View": "250000",
            },
        ]

        report = build_export_report(
            rows,
            hashtag_filters=["#freefire", "#nhasangtaofreefire"],
            event_hashtags=["#ob53"],
            report_mode="complete_previous_day",
            timezone_name="Asia/Ho_Chi_Minh",
            fetch_window_label="7D",
            top_limit=5,
            trend_min_views=200000,
            now=datetime(2026, 4, 12, 9, 0, 0),
        )

        self.assertEqual(report["summary"]["rowsFetched"], 5)
        self.assertEqual(
            report["modules"]["topContentByPlatform"]["1D"]["tiktok"][0]["channelName"],
            "Channel TT A",
        )
        self.assertEqual(
            report["modules"]["topContentByPlatform"]["1D"]["youtube"][0]["view"],
            700000,
        )
        self.assertEqual(report["modules"]["trendVideos7D"][0]["trendRatio"], 4.55)
        self.assertEqual(report["modules"]["dailyViews7D"]["peakDate"], "2026-04-11")
        self.assertEqual(report["modules"]["topKols7D"]["youtube"][0]["totalView"], 950000)
        self.assertEqual(report["modules"]["dailyViews7D"]["lowDate"], "2026-04-05")
        self.assertEqual(report["modules"]["overview7D"]["totalPosts"], 5)
        self.assertEqual(report["modules"]["overview7D"]["totalView"], 1670000)
        self.assertEqual(report["modules"]["overview7D"]["averageView"], 334000)
        self.assertEqual(report["modules"]["dailyViews7D"]["peakPostingHourRange"], "09:00-10:00")
        self.assertNotIn("peakPostingHourRange", report["modules"]["dailyPostCount7D"])

        seatalk_text = render_seatalk_report(report, title="Daily FFVN KOL Report")
        self.assertIn("Top Content 1D", seatalk_text)
        self.assertIn("[Link]", seatalk_text)
        self.assertNotIn("baseline", seatalk_text)
        self.assertIn("Total views", seatalk_text)
        self.assertIn("Peak posting hour", seatalk_text)
        self.assertIn("Highest and lowest total published clips", seatalk_text)

    def test_export_rows_roundtrip_and_daily_windows(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "1",
                "Channel name": "Channel A",
                "Category": "Gameplay_Creator",
                "Post id": "abc",
                "Post type": "VIDEO",
                "Post description": "Hello",
                "Link": "https://example.com",
                "Publish time": "2026-04-11 16:00:00",
                "Hashtag": "#freefire",
                "Comment": "0",
                "Duration (second)": "5",
                "Engagement": "5",
                "Reaction": "4",
                "View": "12",
            }
        ]
        csv_bytes = export_rows_to_csv_bytes(rows)
        parsed = parse_export_csv(csv_bytes)

        self.assertEqual(parsed[0]["Channel name"], "Channel A")
        self.assertEqual(
            build_daily_windows("2026-04-09", "2026-04-11"),
            [("2026-04-09", "2026-04-09"), ("2026-04-10", "2026-04-10"), ("2026-04-11", "2026-04-11")],
        )

    def test_dedupe_export_rows_uses_post_and_link(self):
        rows = [
            {"Post id": "1", "Link": "https://example.com/a", "Channel id": "10"},
            {"Post id": "1", "Link": "https://example.com/a", "Channel id": "10"},
            {"Post id": "2", "Link": "https://example.com/b", "Channel id": "10"},
        ]
        deduped = dedupe_export_rows(rows)
        self.assertEqual(len(deduped), 2)


if __name__ == "__main__":
    unittest.main()
