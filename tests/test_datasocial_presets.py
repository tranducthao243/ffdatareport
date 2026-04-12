import unittest

from datasocial.cli import build_parser
from datasocial.presets import apply_preset_defaults, load_preset


class DatasocialPresetsTests(unittest.TestCase):
    def test_ffvn_daily_preset_applies_defaults(self):
        parser = build_parser()
        args = parser.parse_args([])
        preset = load_preset("ffvn_daily")

        apply_preset_defaults(args, preset)

        self.assertEqual(args.app_id, 2)
        self.assertEqual(args.app_slug, "ffvn")
        self.assertTrue(args.use_export)
        self.assertTrue(args.chunk_by_category)
        self.assertTrue(args.chunk_by_day)
        self.assertEqual(args.fetch_window, "7D")
        self.assertEqual(args.seatalk_title, "Daily FFVN KOL Report")
        self.assertEqual(str(args.save_export), "outputs\\ffvn_daily_latest.csv")
        self.assertEqual(str(args.save_report), "outputs\\ffvn_daily_latest.json")


if __name__ == "__main__":
    unittest.main()
