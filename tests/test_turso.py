"""Turso client: retry semantics, envelope handling, argument encoding."""
import unittest
from unittest.mock import patch

from tfex_common import turso


class _Resp:
    def __init__(self, status_code=200, body=None, headers=None, text=""):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._body


OK_BODY = {
    "results": [{
        "type": "ok",
        "response": {"result": {
            "cols": [{"name": "x"}, {"name": "y"}],
            "rows": [[{"type": "integer", "value": "7"},
                      {"type": "text", "value": "hello"}]],
        }},
    }]
}


class TestUrlAndEncoding(unittest.TestCase):

    def test_normalize_libsql(self):
        self.assertEqual(turso.normalize_url("libsql://db.turso.io"),
                         "https://db.turso.io/v2/pipeline")
        self.assertEqual(turso.normalize_url("https://db.turso.io/"),
                         "https://db.turso.io/v2/pipeline")
        self.assertEqual(turso.normalize_url("https://db.turso.io/v2/pipeline"),
                         "https://db.turso.io/v2/pipeline")

    def test_to_arg_types(self):
        self.assertEqual(turso.to_arg(None), {"type": "null"})
        self.assertEqual(turso.to_arg(True), {"type": "integer", "value": "1"})
        self.assertEqual(turso.to_arg(5), {"type": "integer", "value": "5"})
        self.assertEqual(turso.to_arg(1.5), {"type": "float", "value": 1.5})
        self.assertEqual(turso.to_arg("x"), {"type": "text", "value": "x"})
        self.assertEqual(turso.to_arg(float("nan")), {"type": "null"})
        self.assertEqual(turso.to_arg(float("inf")), {"type": "null"})


class TestExecute(unittest.TestCase):

    def test_success(self):
        with patch.object(turso.requests, "post", return_value=_Resp(body=OK_BODY)):
            cols, rows = turso.execute_sql("http://x", "t", "SELECT 1")
        self.assertEqual(cols, ["x", "y"])
        self.assertEqual(rows, [[7, "hello"]])

    def test_empty_envelope_raises_clear_error(self):
        with patch.object(turso.requests, "post", return_value=_Resp(body={"foo": 1})):
            with self.assertRaises(RuntimeError) as ctx:
                turso.execute_sql("http://x", "t", "SELECT 1")
        self.assertIn("no results envelope", str(ctx.exception))

    def test_retries_transient_5xx_then_succeeds(self):
        seq = [_Resp(503, text="unavailable"), _Resp(502, text="bad gateway"),
               _Resp(body=OK_BODY)]
        with patch.object(turso.requests, "post", side_effect=seq), \
             patch.object(turso.time, "sleep", lambda *_: None):
            cols, rows = turso.execute_sql("http://x", "t", "SELECT 1")
        self.assertEqual(rows, [[7, "hello"]])

    def test_gives_up_after_max_attempts(self):
        with patch.object(turso.requests, "post", return_value=_Resp(500, text="boom")), \
             patch.object(turso.time, "sleep", lambda *_: None):
            with self.assertRaises(RuntimeError):
                turso.execute_sql("http://x", "t", "SELECT 1", max_attempts=2)

    def test_sql_error_is_not_retried(self):
        calls = {"n": 0}
        err = _Resp(body={"results": [{"type": "error", "error": "no such table"}]})

        def fake_post(*a, **k):
            calls["n"] += 1
            return err

        with patch.object(turso.requests, "post", side_effect=fake_post):
            with self.assertRaises(RuntimeError):
                turso.execute_sql("http://x", "t", "SELECT 1")
        self.assertEqual(calls["n"], 1)

    def test_4xx_is_not_retried(self):
        calls = {"n": 0}

        def fake_post(*a, **k):
            calls["n"] += 1
            return _Resp(400, text="bad request")

        with patch.object(turso.requests, "post", side_effect=fake_post):
            with self.assertRaises(RuntimeError):
                turso.execute_sql("http://x", "t", "SELECT 1")
        self.assertEqual(calls["n"], 1)

    def test_retry_after_is_honoured(self):
        delays = []
        seq = [_Resp(429, headers={"Retry-After": "7"}, text="slow down"), _Resp(body=OK_BODY)]
        with patch.object(turso.requests, "post", side_effect=seq), \
             patch.object(turso.time, "sleep", lambda d: delays.append(d)):
            turso.execute_sql("http://x", "t", "SELECT 1")
        self.assertEqual(delays, [7.0])

    def test_network_error_retried(self):
        seq = [turso.requests.ConnectionError("boom"), _Resp(body=OK_BODY)]
        with patch.object(turso.requests, "post", side_effect=seq), \
             patch.object(turso.time, "sleep", lambda *_: None):
            cols, rows = turso.execute_sql("http://x", "t", "SELECT 1")
        self.assertEqual(cols, ["x", "y"])

    def test_empty_sql_rejected(self):
        with self.assertRaises(ValueError):
            turso.execute_sql("http://x", "t", "   ")


if __name__ == "__main__":
    unittest.main()
