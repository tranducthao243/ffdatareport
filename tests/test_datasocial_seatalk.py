import unittest

from datasocial.formatter import render_seatalk_report


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


if __name__ == "__main__":
    unittest.main()
