"""Calendar: expiry dates must be identical across every repo that consumes them."""
import datetime
import unittest
import warnings

from tfex_common import calendar as cal
from tfex_common.constants import BKK_TZ, SET_HOLIDAYS


class TestPenultimateBusinessDay(unittest.TestCase):

    def test_dec_2026_skips_the_nye_holiday(self):
        # 2026-12-31 is a holiday and 2026-12-30 is the last business day
        self.assertEqual(cal.get_penultimate_business_day(2026, 12), datetime.date(2026, 12, 29))

    def test_mar_2027_has_no_holidays(self):
        self.assertEqual(cal.get_penultimate_business_day(2027, 3), datetime.date(2027, 3, 30))

    def test_dec_2027_matches_the_repo1_expectation(self):
        # tfex-eod-collector PR #1 asserted S50Z27 expiry = 2027-12-29
        self.assertEqual(cal.get_penultimate_business_day(2027, 12), datetime.date(2027, 12, 29))

    def test_holiday_inside_month_shifts_expiry(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # holidays=set() triggers the empty-table warning
            plain = cal.get_penultimate_business_day(2026, 10, holidays=set())
        with_holidays = cal.get_penultimate_business_day(2026, 10)
        self.assertLessEqual(with_holidays, plain)

    def test_year_outside_table_warns_but_still_returns(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = cal.get_penultimate_business_day(2031, 3)
        self.assertIsInstance(result, datetime.date)
        self.assertTrue(any("no data for 2031" in str(w.message) for w in caught))


class TestSeriesExpiry(unittest.TestCase):

    def test_z26(self):
        self.assertEqual(cal.get_series_expiry_date("Z26", datetime.date(2026, 11, 20)),
                         datetime.date(2026, 12, 29))

    def test_h27_rolls_into_next_year(self):
        self.assertEqual(cal.get_series_expiry_date("H27", datetime.date(2026, 11, 20)),
                         datetime.date(2027, 3, 30))

    def test_parse_expiry_is_1630_bkk(self):
        dt = cal.parse_series_expiry("Z26", datetime.date(2026, 11, 20))
        self.assertEqual((dt.hour, dt.minute), (16, 30))
        self.assertEqual(dt.tzinfo, BKK_TZ)

    def test_invalid_series_raises(self):
        with self.assertRaises(ValueError):
            cal.get_series_expiry_date("X26", datetime.date(2026, 11, 20))
        with self.assertRaises(ValueError):
            cal.get_series_expiry_date("ZXX", datetime.date(2026, 11, 20))


class TestActiveSeries(unittest.TestCase):

    def test_front_and_next_on_nov_2026(self):
        now = datetime.datetime(2026, 11, 20, 10, 0, tzinfo=BKK_TZ)
        series, front, nxt = cal.resolve_active_series_candidates(now)
        self.assertEqual(front, "Z26")
        self.assertEqual(nxt, "H27")
        self.assertEqual(series[:4], ["Z26", "H27", "M27", "U27"])

    def test_front_rolls_after_expiry_day_close(self):
        after = datetime.datetime(2026, 12, 29, 17, 0, tzinfo=BKK_TZ)  # Z26 expired 16:30
        _, front, nxt = cal.resolve_active_series_candidates(after)
        self.assertEqual(front, "H27")
        self.assertEqual(nxt, "M27")

    def test_holiday_table_is_shared(self):
        self.assertIs(cal.SET_HOLIDAYS, SET_HOLIDAYS)


if __name__ == "__main__":
    unittest.main()
