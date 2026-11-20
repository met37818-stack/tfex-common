"""THOR unit handling — the bug that broke the discount factor in four repositories."""
import math
import unittest

from tfex_common import THOR_MAX_PCT
from tfex_common.thor import (
    fetch_thor_rates_record,
    parse_thor_row,
    select_dynamic_thor_rate,
    to_decimal_rate,
)


class TestTHORUnit(unittest.TestCase):

    def test_below_half_percent_is_still_percent(self):
        record = {"overnight": 1.50, "1m": 0.45, "3m": 0.90, "6m": 1.20}
        rate, tenor = select_dynamic_thor_rate(record, dte=30)
        self.assertEqual(tenor, "1M")
        self.assertAlmostEqual(rate, 0.0045, places=9)

    def test_normal_rate_unchanged(self):
        rate, _ = select_dynamic_thor_rate({"1m": 0.994}, dte=30)
        self.assertAlmostEqual(rate, 0.00994, places=9)

    def test_tiny_rate_not_inflated(self):
        rate, _ = select_dynamic_thor_rate({"6m": 0.09}, dte=200)
        self.assertAlmostEqual(rate, 0.0009, places=9)

    def test_absurd_rate_raises(self):
        with self.assertRaises(ValueError):
            to_decimal_rate(THOR_MAX_PCT + 0.1, "1m")
        with self.assertRaises(ValueError):
            select_dynamic_thor_rate({"1m": 45.0}, dte=30)

    def test_none_zero_negative_become_none(self):
        for bad in (None, 0, 0.0, -1.0):
            self.assertIsNone(to_decimal_rate(bad))

    def test_discount_factor_impact_of_the_old_bug(self):
        """0.45 read as 45% collapsed exp(-r*T) from 0.999630 to 0.963689 at 30 DTE."""
        T = 30 / 365.0
        correct = math.exp(-0.0045 * T)
        buggy = math.exp(-0.45 * T)
        self.assertLess(abs(correct - buggy) * 50.0, 2.0)   # 1.80 index points at |F-K|=50
        self.assertGreater(abs(correct - buggy) * 50.0, 0.60)  # above the 3-leg hurdle


class TestTenorSelection(unittest.TestCase):

    def setUp(self):
        self.record = {"overnight": 1.0, "1m": 0.8, "3m": 0.9, "6m": 1.1}

    def test_short_dte_prefers_1m(self):
        self.assertEqual(select_dynamic_thor_rate(self.record, 10)[1], "1M")

    def test_mid_dte_prefers_3m(self):
        self.assertEqual(select_dynamic_thor_rate(self.record, 60)[1], "3M")

    def test_long_dte_prefers_6m(self):
        self.assertEqual(select_dynamic_thor_rate(self.record, 120)[1], "6M")
        self.assertEqual(select_dynamic_thor_rate(self.record, 300)[1], "6M")

    def test_fallback_when_preferred_tenor_missing(self):
        rate, tenor = select_dynamic_thor_rate({"overnight": 1.0}, 200)
        self.assertEqual(tenor, "ON")
        self.assertAlmostEqual(rate, 0.01, places=9)

    def test_all_missing_raises(self):
        with self.assertRaises(ValueError):
            select_dynamic_thor_rate({}, 30)


class TestTHORFetch(unittest.TestCase):

    def test_parse_row(self):
        rec = parse_thor_row([0.994, 1.1, None, 1.5])
        self.assertEqual(rec, {"overnight": 0.994, "1m": 1.1, "3m": None, "6m": 1.5})

    def test_fetch_uses_injected_executor(self):
        calls = {}

        def fake_execute(url, token, sql, args=None):
            calls["sql"] = sql
            return (["a", "b", "c", "d"], [[0.994, 1.0, 1.1, 1.2]])

        rec = fetch_thor_rates_record(fake_execute, "http://x", "t")
        self.assertEqual(rec["overnight"], 0.994)
        self.assertIn("eod_thor_rates", calls["sql"])

    def test_fetch_raises_when_null(self):
        def fake_execute(url, token, sql, args=None):
            return (["a"], [[None]])

        with self.assertRaises(ValueError):
            fetch_thor_rates_record(fake_execute, "http://x", "t")


if __name__ == "__main__":
    unittest.main()
