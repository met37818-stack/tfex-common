"""
Tests for the shared report template.

The template exists so that two different jobs cannot drift into two different
ideas of what a message should say. These tests pin the contract: section order,
omission of empty sections, the ready/pending counters, and the Telegram limit.
"""
import unittest

from tfex_common.report import (
    DIVIDER,
    TELEGRAM_LIMIT,
    TRUNCATION_NOTICE,
    Report,
    bullet,
    rr,
    sub,
)


def _report(**kw):
    base = dict(
        title="SET50 · S50Z26 · ข้อมูลสิ้นวัน 2026-11-20",
        subtitle="ออกรายงาน 06:46 น.",
        measured=[bullet("Settlement <code>991.1</code>")],
        inferred=[bullet("Flow: Neutral")],
        plan=[bullet("Long | 980–982 | Stop Loss &lt;970")],
        watch=["ปิดเหนือ <code>1016.3</code>"],
        footer="🌐 กราฟ",
    )
    base.update(kw)
    return Report(**base)


class TestLayout(unittest.TestCase):
    def test_section_order_is_fixed(self):
        msg = _report(pending=["RV (0/10 บาร์)"]).build()
        order = ["📏", "🧠", "🎯", "⏳", "🔁"]
        positions = [msg.index(icon) for icon in order]
        self.assertEqual(positions, sorted(positions), "sections must render in order")

    def test_empty_sections_are_omitted(self):
        msg = _report(inferred=[], pending=[]).build()
        self.assertNotIn("อนุมาน", msg)
        self.assertNotIn("ยังไม่พร้อม:", msg)
        self.assertIn("วัดได้", msg)
        self.assertIn("🎯 <b>แผน</b>", msg)

    def test_no_double_blank_lines(self):
        msg = _report(inferred=[], pending=[], watch=[]).build()
        self.assertNotIn("\n\n\n", msg)

    def test_divider_present_once_at_each_end(self):
        msg = _report().build()
        self.assertEqual(msg.count(DIVIDER), 2)

    def test_footer_last(self):
        msg = _report().build()
        self.assertTrue(msg.rstrip().endswith("🌐 กราฟ"))

    def test_caller_tags_are_not_escaped(self):
        msg = _report().build()
        self.assertIn("<code>991.1</code>", msg)
        self.assertIn("<b>", msg)


class TestCounters(unittest.TestCase):
    def test_counts_only_appear_when_provided(self):
        msg = _report().build()
        self.assertNotIn("ข้อมูลพร้อม", msg)

    def test_ready_and_pending_are_both_reported(self):
        msg = _report(ready_sections=6, pending=["RV (0/10 บาร์)", "Late Session"]).build()
        self.assertIn("ข้อมูลพร้อม 6 ส่วน", msg)
        self.assertIn("ยังไม่พร้อม 2", msg)

    def test_pending_list_is_deduplicated(self):
        r = _report()
        r.add_pending("RV (0/10 บาร์)")
        r.add_pending("RV (0/10 บาร์)")
        self.assertEqual(r.pending, ["RV (0/10 บาร์)"])


class TestTelegramLimit(unittest.TestCase):
    def test_short_message_is_untouched(self):
        msg = _report().build()
        self.assertEqual(_report().build_telegram(), msg)

    def test_long_message_is_trimmed_from_the_end_of_measured(self):
        r = _report(measured=[bullet(f"line {i} " + "x" * 80) for i in range(40)])
        msg = r.build_telegram()
        self.assertLessEqual(len(msg), TELEGRAM_LIMIT)
        self.assertIn("🎯", msg, "the plan must survive trimming")

    def test_the_report_object_is_not_mutated_by_rendering(self):
        r = _report(measured=[bullet(f"line {i} " + "x" * 80) for i in range(40)])
        before = list(r.measured)
        r.build_telegram()
        self.assertEqual(r.measured, before)

    def test_unsplittable_message_is_cut_with_a_notice(self):
        r = Report(title="x", measured=[bullet("y" * 5000)])
        msg = r.build_telegram()
        self.assertLessEqual(len(msg), TELEGRAM_LIMIT)
        self.assertIn("เกินขีดจำกัด Telegram", TRUNCATION_NOTICE)
        self.assertIn(TRUNCATION_NOTICE, msg)


class TestRiskReward(unittest.TestCase):
    def test_long(self):
        self.assertEqual(rr(target=1000, entry=982, stop=970), "1:1.5")

    def test_short_is_direction_agnostic(self):
        # entry above stop, target below: must not return n/a
        self.assertEqual(rr(target=980, entry=1000, stop=1003), "1:6.7")

    def test_unbracketed_levels_are_reported_as_na(self):
        self.assertEqual(rr(target=990, entry=990, stop=990), "n/a")
        # entry 1000, target 980, stop 1010 is a legitimate short: 1:2.0
        self.assertEqual(rr(target=980, entry=1000, stop=1010), "1:2.0")
        self.assertEqual(rr(target=1000, entry=1000, stop=1010), "n/a")

    def test_bad_input_is_na_not_a_crash(self):
        self.assertEqual(rr(target=None, entry=1, stop=2), "n/a")


class TestFluentHelpers(unittest.TestCase):
    def test_chained_adds(self):
        r = (Report(title="t").add_measured("m").add_inferred("i")
             .add_plan("p").add_pending("x").add_watch("w"))
        msg = r.build()
        for token in ("m", "i", "p", "x", "w"):
            self.assertIn(token, msg)

    def test_bullet_and_sub_indentation(self):
        self.assertTrue(bullet("a").startswith("  • "))
        self.assertTrue(sub("a").startswith("    – "))


if __name__ == "__main__":
    unittest.main()
