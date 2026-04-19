import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.data_chat import answer_data_question
from app.pipeline import build_store_from_export
from datasocial.exporter import export_rows_to_csv_bytes


class DataChatTests(unittest.TestCase):
    def test_answer_clip_count_question_for_current_month(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-1",
                "Channel name": "Jeeker",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "tt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 1",
                "Link": "https://www.tiktok.com/@jeeker/video/1",
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
                "Platform": "Youtube",
                "Channel id": "yt-1",
                "Channel name": "Jeeker",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "yt-post-1",
                "Post type": "VIDEO",
                "Post description": "Clip 2",
                "Link": "https://www.youtube.com/shorts/1",
                "Publish time": "2026-04-05 11:00:00",
                "Hashtag": "#freefire",
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

            answer = answer_data_question(
                db_path,
                "Jeeker thang nay da dang bao nhieu clip",
                now=datetime(2026, 4, 19, 9, 0, 0),
            )

            self.assertIsNotNone(answer)
            self.assertIn("Jeeker", answer)
            self.assertIn("So clip da dang: 2", answer)
            self.assertIn("2026-04-01 -> 2026-04-19", answer)

    def test_answer_million_view_question(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-2",
                "Channel name": "Bac Gau",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "tt-post-2",
                "Post type": "VIDEO",
                "Post description": "Clip 1",
                "Link": "https://www.tiktok.com/@bacgau/video/1",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "1500000",
            },
            {
                "ID": "2",
                "Platform": "Tiktok",
                "Channel id": "tt-2",
                "Channel name": "Bac Gau",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "tt-post-3",
                "Post type": "VIDEO",
                "Post description": "Clip 2",
                "Link": "https://www.tiktok.com/@bacgau/video/2",
                "Publish time": "2026-04-09 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "900000",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "master.csv"
            db_path = root / "master.sqlite"
            csv_path.write_bytes(export_rows_to_csv_bytes(rows))
            build_store_from_export(csv_path, db_path, timezone_name="Asia/Ho_Chi_Minh")

            answer = answer_data_question(
                db_path,
                "Bac Gau thang nay co bao nhieu clip trieu view",
                now=datetime(2026, 4, 19, 9, 0, 0),
            )

            self.assertIsNotNone(answer)
            self.assertIn("So clip dat tu 1M view: 1", answer)
            self.assertIn("https://www.tiktok.com/@bacgau/video/1", answer)

    def test_answer_total_view_question(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-3",
                "Channel name": "Jeeker",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "tt-post-4",
                "Post type": "VIDEO",
                "Post description": "Clip 1",
                "Link": "https://www.tiktok.com/@jeeker/video/4",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "1500000",
            },
            {
                "ID": "2",
                "Platform": "Youtube",
                "Channel id": "yt-3",
                "Channel name": "Jeeker",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "yt-post-3",
                "Post type": "VIDEO",
                "Post description": "Clip 2",
                "Link": "https://www.youtube.com/shorts/3",
                "Publish time": "2026-04-10 10:00:00",
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

            answer = answer_data_question(
                db_path,
                "Jeeker thang nay tong view bao nhieu",
                now=datetime(2026, 4, 19, 9, 0, 0),
            )

            self.assertIsNotNone(answer)
            self.assertIn("Tong view: 2.00M", answer)
            self.assertIn("So clip: 2", answer)

    def test_answer_top_clips_question(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-4",
                "Channel name": "Jeeker",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "tt-post-5",
                "Post type": "VIDEO",
                "Post description": "Clip 1",
                "Link": "https://www.tiktok.com/@jeeker/video/5",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "1500000",
            },
            {
                "ID": "2",
                "Platform": "Tiktok",
                "Channel id": "tt-4",
                "Channel name": "Jeeker",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "tt-post-6",
                "Post type": "VIDEO",
                "Post description": "Clip 2",
                "Link": "https://www.tiktok.com/@jeeker/video/6",
                "Publish time": "2026-04-10 10:00:00",
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

            answer = answer_data_question(
                db_path,
                "Top clip cua Jeeker trong thang nay",
                now=datetime(2026, 4, 19, 9, 0, 0),
            )

            self.assertIsNotNone(answer)
            self.assertIn("Top clip cua kenh", answer)
            self.assertIn("https://www.tiktok.com/@jeeker/video/5", answer)

    def test_answer_compare_channels_question(self):
        rows = [
            {
                "ID": "1",
                "Platform": "Tiktok",
                "Channel id": "tt-5",
                "Channel name": "Jeeker",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "tt-post-7",
                "Post type": "VIDEO",
                "Post description": "Clip 1",
                "Link": "https://www.tiktok.com/@jeeker/video/7",
                "Publish time": "2026-04-17 10:00:00",
                "Hashtag": "#freefire",
                "Comment": "10",
                "Duration (second)": "30",
                "Engagement": "120",
                "Reaction": "90",
                "View": "1500000",
            },
            {
                "ID": "2",
                "Platform": "Tiktok",
                "Channel id": "tt-6",
                "Channel name": "Bac Gau",
                "Category": "Gameplay_Creator",
                "__category_id": "14",
                "Post id": "tt-post-8",
                "Post type": "VIDEO",
                "Post description": "Clip 2",
                "Link": "https://www.tiktok.com/@bacgau/video/8",
                "Publish time": "2026-04-10 10:00:00",
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

            answer = answer_data_question(
                db_path,
                "So sanh Jeeker va Bac Gau trong thang nay",
                now=datetime(2026, 4, 19, 9, 0, 0),
            )

            self.assertIsNotNone(answer)
            self.assertIn("So sanh Jeeker va Bac Gau", answer)
            self.assertIn("Jeeker dang cao hon ve tong view", answer)


if __name__ == "__main__":
    unittest.main()
