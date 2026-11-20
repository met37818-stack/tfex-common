"""Telegram dispatch: a failure must never leak the bot token or raise."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from tfex_common import telegram

TOKEN = "123456789:AAFakeTokenForTestingOnly_abcdefghijklm"


class TestEscapeHtml(unittest.TestCase):

    def test_keeps_supported_tags(self):
        out = telegram.escape_html("<b>bold</b> <code>x</code>")
        self.assertEqual(out, "<b>bold</b> <code>x</code>")

    def test_escapes_stray_angle_brackets(self):
        out = telegram.escape_html("a < b and c > d")
        self.assertEqual(out, "a &lt; b and c &gt; d")

    def test_escapes_ampersand_but_not_entities(self):
        self.assertEqual(telegram.escape_html("P&L"), "P&amp;L")
        self.assertEqual(telegram.escape_html("&amp;"), "&amp;")

    def test_none_is_empty(self):
        self.assertEqual(telegram.escape_html(None), "")


class TestSendAlert(unittest.TestCase):

    def test_connection_error_does_not_leak_token(self):
        buf = io.StringIO()

        def boom(*a, **k):
            raise telegram.requests.ConnectionError(
                "Max retries exceeded with url: "
                f"/bot{TOKEN}/sendMessage")

        with patch.object(telegram.requests, "post", side_effect=boom), redirect_stdout(buf):
            ok = telegram.send_alert(TOKEN, "1", "<b>hi</b>")

        out = buf.getvalue()
        self.assertFalse(ok, "ต้องคืน False ไม่ raise")
        self.assertNotIn(TOKEN, out, "token ต้องไม่หลุดลง log")
        self.assertIn("ConnectionError", out)

    def test_http_error_logs_truncated_body(self):
        buf = io.StringIO()

        class R:
            status_code = 400
            text = "bad" * 500

        with patch.object(telegram.requests, "post", return_value=R()), redirect_stdout(buf):
            ok = telegram.send_alert(TOKEN, "1", "x")
        self.assertFalse(ok)
        self.assertLess(len(buf.getvalue()), 400)

    def test_success(self):
        class R:
            status_code = 200
            text = '{"ok": true}'

        buf = io.StringIO()
        with patch.object(telegram.requests, "post", return_value=R()), redirect_stdout(buf):
            self.assertTrue(telegram.send_alert(TOKEN, "1", "x"))

    def test_missing_credentials_returns_false(self):
        self.assertFalse(telegram.send_alert("", "1", "x"))
        self.assertFalse(telegram.send_alert(TOKEN, "", "x"))

    def test_escape_flag_applies_escaping(self):
        captured = {}

        class R:
            status_code = 200
            text = ""

        def fake_post(url, json=None, timeout=None):
            captured.update(json)
            return R()

        with patch.object(telegram.requests, "post", side_effect=fake_post), redirect_stdout(io.StringIO()):
            telegram.send_alert(TOKEN, "1", "a < b", escape=True)
        self.assertIn("&lt;", captured["text"])


class TestSendDocument(unittest.TestCase):

    def test_failure_is_swallowed(self):
        def boom(*a, **k):
            raise telegram.requests.Timeout(f"url /bot{TOKEN}/sendDocument timed out")

        buf = io.StringIO()
        with patch.object(telegram.requests, "post", side_effect=boom), redirect_stdout(buf):
            ok = telegram.send_document(TOKEN, "1", b"x", "f.xlsx")
        self.assertFalse(ok)
        self.assertNotIn(TOKEN, buf.getvalue())


if __name__ == "__main__":
    unittest.main()
