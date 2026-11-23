"""
Tests for the run lifecycle notifications.

Three separate messages were requested (started / finished / failed), and the hard
requirement is that none of them can break the job: a Telegram outage must not turn
a successful session into a failed one, and an exception message must not carry the
bot token into a public repository's log or chat.
"""
import unittest

from tfex_common import lifecycle
from tfex_common.lifecycle import Lifecycle, run_failed, run_finished, run_started, safe_error_text


class _Capture:
    def __init__(self, ok=True):
        self.calls = []
        self.ok = ok

    def __call__(self, token, chat, text):
        self.calls.append((token, chat, text))
        return self.ok


class TestStarted(unittest.TestCase):
    def setUp(self):
        self.cap = _Capture()
        self._orig = lifecycle._send
        lifecycle._send = self.cap

    def tearDown(self):
        lifecycle._send = self._orig

    def test_one_message_with_job_and_mode(self):
        run_started("tfex-arb-opp", mode="EVENING_WORKER",
                    detail={"date": "2026-11-20", "workers": 8},
                    bot_token="t", chat_id="c")
        self.assertEqual(len(self.cap.calls), 1)
        text = self.cap.calls[0][2]
        self.assertIn("tfex-arb-opp", text)
        self.assertIn("เริ่มทำงาน", text)
        self.assertIn("EVENING_WORKER", text)
        self.assertIn("2026-11-20", text)
        self.assertIn("workers", text)

    def test_no_credentials_means_no_call(self):
        run_started("job", bot_token="", chat_id="")
        self.assertEqual(self.cap.calls, [])

    def test_sender_exception_is_swallowed(self):
        def boom(*a, **k):
            raise RuntimeError("network down")
        lifecycle._send = boom
        self.assertFalse(run_started("job", bot_token="t", chat_id="c"))

    def test_transport_false_is_reported(self):
        lifecycle._send = _Capture(ok=False)
        self.assertFalse(run_started("job", bot_token="t", chat_id="c"))


class TestFinished(unittest.TestCase):
    def setUp(self):
        self.cap = _Capture()
        self._orig = lifecycle._send
        lifecycle._send = self.cap

    def tearDown(self):
        lifecycle._send = self._orig

    def test_carries_exit_code_and_duration(self):
        run_finished("tfex-intraday-collector", 754.2, mode="session",
                     summary={"bars": 355, "errors": 0}, bot_token="t", chat_id="c")
        text = self.cap.calls[0][2]
        self.assertIn("จบงาน", text)
        self.assertIn("exit 0", text)
        self.assertIn("754.2 วิ", text)
        self.assertIn("bars", text)

    def test_missing_summary_says_so(self):
        run_finished("job", 1.0, bot_token="t", chat_id="c")
        self.assertIn("ไม่มีตัวนับเพิ่มเติม", self.cap.calls[0][2])


class TestFailed(unittest.TestCase):
    def setUp(self):
        self.cap = _Capture()
        self._orig = lifecycle._send
        lifecycle._send = self.cap

    def tearDown(self):
        lifecycle._send = self._orig

    def test_reports_stage_and_error(self):
        run_failed("job", ValueError("boom"), stage="Section 4", exit_code=3,
                   duration_s=12.0, mode="session", bot_token="t", chat_id="c")
        text = self.cap.calls[0][2]
        self.assertIn("ล้มเหลว", text)
        self.assertIn("Section 4", text)
        self.assertIn("ValueError: boom", text)
        self.assertIn("exit 3", text)


class TestErrorSanitising(unittest.TestCase):
    def test_bot_token_never_survives(self):
        text = safe_error_text(RuntimeError(
            "HTTPSConnectionPool: Max retries exceeded with url: /bot123456:AAHsecretTOKEN/sendMessage"))
        self.assertNotIn("AAHsecretTOKEN", text)
        self.assertIn("bot<redacted>", text)

    def test_urls_are_stripped(self):
        text = safe_error_text("failed at https://db.turso.io/v2/pipeline?x=1")
        self.assertNotIn("turso.io", text)
        self.assertIn("<url>", text)

    def test_long_message_is_truncated(self):
        text = safe_error_text("x" * 1000)
        self.assertLessEqual(len(text), 301)

    def test_plain_string_is_accepted(self):
        self.assertIn("something broke", safe_error_text("something broke"))


class TestContextManager(unittest.TestCase):
    def setUp(self):
        self.cap = _Capture()
        self._orig = lifecycle._send
        lifecycle._send = self.cap

    def tearDown(self):
        lifecycle._send = self._orig

    def test_success_sends_started_then_finished(self):
        with Lifecycle("job", "mode", bot_token="t", chat_id="c"):
            pass
        texts = [c[2] for c in self.cap.calls]
        self.assertEqual(len(texts), 2)
        self.assertIn("เริ่มทำงาน", texts[0])
        self.assertIn("จบงาน", texts[1])

    def test_exception_sends_started_then_failed_and_reraises(self):
        with self.assertRaises(RuntimeError):
            with Lifecycle("job", bot_token="t", chat_id="c"):
                raise RuntimeError("kaboom")
        texts = [c[2] for c in self.cap.calls]
        self.assertEqual(len(texts), 2)
        self.assertIn("เริ่มทำงาน", texts[0])
        self.assertIn("ล้มเหลว", texts[1])

    def test_nonzero_exit_is_a_failure_not_a_finish(self):
        with self.assertRaises(SystemExit):
            with Lifecycle("job", bot_token="t", chat_id="c"):
                raise SystemExit(3)
        texts = [c[2] for c in self.cap.calls]
        self.assertIn("ล้มเหลว", texts[1])
        self.assertIn("exit 3", texts[1])

    def test_exit_zero_counts_as_finished(self):
        with self.assertRaises(SystemExit):
            with Lifecycle("job", bot_token="t", chat_id="c"):
                raise SystemExit(0)
        self.assertIn("จบงาน", self.cap.calls[1][2])

    def test_explicit_finish_is_not_duplicated_by_exit(self):
        with Lifecycle("job", bot_token="t", chat_id="c") as life:
            life.finished({"bars": 12})
        texts = [c[2] for c in self.cap.calls]
        self.assertEqual(len(texts), 2, "started + one finished, not two")
        self.assertIn("bars", texts[1])

    def test_explicit_fail_is_not_duplicated_by_exit(self):
        with self.assertRaises(RuntimeError):
            with Lifecycle("job", bot_token="t", chat_id="c") as life:
                life.failed("explicit reason")
                raise RuntimeError("then a real one")
        texts = [c[2] for c in self.cap.calls]
        self.assertEqual(len(texts), 2)

    def test_disabled_sends_nothing(self):
        with Lifecycle("job", enabled=False, bot_token="t", chat_id="c"):
            pass
        self.assertEqual(self.cap.calls, [])


if __name__ == "__main__":
    unittest.main()
