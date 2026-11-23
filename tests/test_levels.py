"""
Tests for the shared level book and plan-leg formatting.

Two real defects are pinned here: a strike printed with a bare "(1,085)" next to it
(the OI had no label, so a reader could not tell what the number was), and a short
leg whose risk-reward came out "n/a" because the helper assumed a long.
"""
import unittest

from tfex_common.levels import Level, LevelBook, plan_leg


def _book(**kw):
    base = dict(
        res2=Level(1010, 1085), res1=Level(1000, 983),
        sup1=Level(980, 1602), sup2=Level(970, 1479),
        put_wall=960, call_wall=1100, max_pain=1020,
    )
    base.update(kw)
    return LevelBook(**base)


class TestLevelBook(unittest.TestCase):
    def test_ladder_labels_the_open_interest(self):
        line = _book().ladder_line()
        self.assertIn("ต้าน 2 <code>1010</code> (OI 1,085)", line)
        self.assertIn("รับ 2 <code>970</code> (OI 1,479)", line)
        self.assertNotIn("(1,085) |", line.replace("(OI 1,085)", ""), "OI must never be a bare parenthetical")

    def test_ladder_order_is_resistance_then_support(self):
        line = _book().ladder_line()
        order = [line.index(tok) for tok in ("ต้าน 2", "ต้าน 1", "รับ 1", "รับ 2")]
        self.assertEqual(order, sorted(order))

    def test_level_without_oi_renders_alone(self):
        self.assertEqual(Level(1000).render(), "<code>1000</code>")

    def test_walls_line_skips_unknown_values(self):
        line = _book(put_wall=None, max_pain=1020).walls_line()
        self.assertNotIn("Put Wall", line)
        self.assertIn("Call Wall", line)
        self.assertIn("Max Pain", line)

    def test_walls_line_can_be_empty(self):
        self.assertEqual(_book(put_wall=None, call_wall=None, max_pain=None).walls_line(), "")

    def test_nearest_reports_the_side(self):
        label, level = _book().nearest(995)
        self.assertEqual(label, "ต้าน 1")
        self.assertEqual(level.price, 1000)

        label, level = _book().nearest(965)
        self.assertEqual(label, "รับ 2")

    def test_levels_are_sorted_from_low_to_high(self):
        prices = [lv.price for lv in _book().levels()]
        self.assertEqual(prices, sorted(prices))


class TestPlanLeg(unittest.TestCase):
    def test_long_leg_states_the_stop_below(self):
        line = plan_leg("long", 980.0, 982.0, 970, [1000, 1020], style="ดักรับ (ครึ่งไซส์)", emoji="🟢")
        self.assertIn("Stop Loss &lt;<code>970</code>", line, "long stop must read '<'")
        self.assertIn("เป้า <code>1000</code> (R:R 1:1.5)", line)
        self.assertIn("→ <code>1020</code> (R:R 1:3.2)", line)

    def test_short_leg_states_the_stop_above_and_keeps_its_ratio(self):
        line = plan_leg("short", 1000.0, 1000.2, 1003.0, [980], emoji="🔴")
        self.assertIn("Stop Loss &gt;<code>1003</code>", line)
        self.assertIn("R:R 1:6.7", line)
        self.assertNotIn("R:R n/a", line)

    def test_entry_zone_is_ordered_small_to_large(self):
        line = plan_leg("long", 982.0, 980.0, 970, [1000])
        self.assertLess(line.index("<code>980.0</code>"), line.index("<code>982.0</code>"))

    def test_target_note_is_appended(self):
        line = plan_leg("long", 980, 982, 970, [(1020, "<i>Max Pain</i>")])
        self.assertIn("(R:R 1:3.2) <i>Max Pain</i>", line)

    def test_unbracketed_target_reports_na(self):
        line = plan_leg("long", 980, 982, 970, [982])
        self.assertIn("R:R n/a", line)


if __name__ == "__main__":
    unittest.main()
