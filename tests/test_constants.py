"""Constants: holiday table completeness, Thai timezone, commission hurdles."""
import datetime
import unittest

from tfex_common import constants as C


class TestHolidayTable(unittest.TestCase):

    def test_2026_has_20_holidays_including_oct_16(self):
        # 2026-10-16 was missing from tfex-quant-analytics before the 2026-11-22 review
        y2026 = sorted(h for h in C.SET_HOLIDAYS if h.startswith("2026"))
        self.assertEqual(len(y2026), 20)
        self.assertIn("2026-10-16", C.SET_HOLIDAYS)

    def test_other_years_have_expected_counts(self):
        self.assertEqual(len([h for h in C.SET_HOLIDAYS if h.startswith("2027")]), 18)
        self.assertEqual(len([h for h in C.SET_HOLIDAYS if h.startswith("2028")]), 15)

    def test_all_entries_are_weekdays(self):
        for h in C.SET_HOLIDAYS:
            self.assertLess(datetime.date.fromisoformat(h).weekday(), 5, f"{h} is a weekend")

    def test_weekends_are_not_listed(self):
        for h in C.SET_HOLIDAYS:
            self.assertIsInstance(h, str)


class TestTimeAndCommission(unittest.TestCase):

    def test_bkk_is_utc_plus_7(self):
        self.assertEqual(C.BKK_TZ.utcoffset(None), datetime.timedelta(hours=7))

    def test_commission_hurdles(self):
        self.assertAlmostEqual(C.COMMISSION_PER_LEG_PTS, 0.20, places=6)
        self.assertAlmostEqual(C.COMMISSION_2LEG_PTS, 0.40, places=6)
        self.assertAlmostEqual(C.COMMISSION_3LEG_PTS, 0.60, places=6)
        self.assertAlmostEqual(C.COMMISSION_4LEG_PTS, 0.80, places=6)

    def test_contract_multiplier_is_200_thb_per_point(self):
        self.assertEqual(C.CONTRACT_MULTIPLIER, 200.0)


if __name__ == "__main__":
    unittest.main()
