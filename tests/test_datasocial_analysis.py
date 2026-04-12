import unittest

from datasocial.analysis import build_report
from datasocial.models import PostRecord


class DatasocialAnalysisTests(unittest.TestCase):
    def test_build_report_groups_top_and_low_activity_sections(self):
        posts = [
            PostRecord(
                post_id="1",
                title="Post A",
                url="https://example.com/a",
                created_at="2099-01-10T00:00:00Z",
                metrics={"view": 100},
                raw={"channelId": 1, "alias": "Channel A", "tags": "#freefire #ob53"},
            ),
            PostRecord(
                post_id="2",
                title="Post B",
                url="https://example.com/b",
                created_at="2099-01-09T00:00:00Z",
                metrics={"view": 50},
                raw={"channelId": 1, "alias": "Channel A", "tags": "#freefire"},
            ),
            PostRecord(
                post_id="3",
                title="Post C",
                url="https://example.com/c",
                created_at="2099-01-08T00:00:00Z",
                metrics={"view": 10},
                raw={"channelId": 2, "alias": "Channel B", "tags": "#nhasangtaofreefire"},
            ),
        ]

        report = build_report(
            posts,
            hashtag_filters=["#freefire", "#nhasangtaofreefire"],
            event_hashtags=["#ob53"],
            low_activity_threshold=2,
            top_limit=5,
        )

        self.assertEqual(report["summary"]["totalPostsFetched"], 3)
        self.assertEqual(report["weeklyTopVideos"][0]["title"], "Post A")
        self.assertEqual(report["eventHighlights7Days"][0]["title"], "Post A")
        self.assertEqual(report["lowActivityChannels30Days"][0]["channelName"], "Channel B")


if __name__ == "__main__":
    unittest.main()
