"""Turso (libSQL) v2 HTTP pipeline client with retry/backoff.

Replaces four near-identical copies that all shared the same weaknesses:
  * `data["results"][0]` raised IndexError on an unusual envelope;
  * a single transient 5xx killed the whole job;
  * error messages were truncated nowhere (a 50 KB HTML error page in a log).

SQL errors are deterministic and are never retried; network errors and HTTP 429/5xx
are retried with exponential backoff, honouring Retry-After up to a cap.
"""
import math
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_TIMEOUT = 25
DEFAULT_MAX_ATTEMPTS = 3
RETRY_AFTER_CAP = 30.0


def normalize_url(raw_url: str, path: str = "/v2/pipeline") -> str:
    """Turn a libsql:// or https:// Turso URL into the HTTP pipeline endpoint."""
    if not raw_url:
        raise ValueError("Empty Turso URL")
    url = str(raw_url).strip().rstrip("/")
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    elif not url.startswith(("http://", "https://")):
        # A bare host (e.g. "db.turso.io") appears in a few callers.
        url = "https://" + url
    if url.endswith(path):
        return url
    return url + path


def redact(text: str, token: Optional[str]) -> str:
    """Replace a live bearer token in a response body before it reaches a log."""
    if not text:
        return ""
    out = str(text)
    if token:
        out = out.replace(token, "***")
    return out


def to_arg(val) -> Dict[str, Any]:
    """Encode a Python value as a Turso argument object (NaN/inf become NULL)."""
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": str(int(val))}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return {"type": "null"}
        return {"type": "float", "value": val}
    return {"type": "text", "value": str(val)}


def parse_result(result_item: Dict[str, Any]) -> Tuple[List[str], List[List[Any]]]:
    """Parse a single `results[]` entry into (columns, rows)."""
    payload = (result_item.get("response") or {}).get("result") or {}
    cols = [c.get("name") for c in payload.get("cols", [])]
    rows: List[List[Any]] = []
    for raw_row in payload.get("rows", []):
        row: List[Any] = []
        for cell in raw_row:
            ctype = cell.get("type")
            cval = cell.get("value")
            if ctype == "null" or cval is None:
                row.append(None)
            elif ctype == "integer":
                row.append(int(cval))
            elif ctype == "float":
                row.append(float(cval))
            else:
                row.append(cval)
        rows.append(row)
    return cols, rows


def _retry_delay(attempt: int, retry_after: Optional[str]) -> float:
    if retry_after:
        cleaned = str(retry_after).strip()
        if cleaned.replace(".", "", 1).isdigit():
            return min(float(cleaned), RETRY_AFTER_CAP)
    return min(2.0 ** (attempt - 1), 8.0)


def execute_sql(pipeline_url: str, auth_token: str, sql: str, args: Optional[List[Any]] = None,
                max_attempts: int = DEFAULT_MAX_ATTEMPTS,
                timeout: int = DEFAULT_TIMEOUT) -> Tuple[List[str], List[List[Any]]]:
    """
    Execute one statement through the Turso v2 pipeline.

    Returns (columns, rows). Raises RuntimeError for SQL errors and unexpected
    envelopes, and re-raises the last transport error when every attempt fails.
    """
    if not pipeline_url:
        raise ValueError("Turso pipeline_url is required")
    if not sql or not str(sql).strip():
        raise ValueError("Empty SQL statement")

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "requests": [
            {"type": "execute", "stmt": {"sql": str(sql).strip(),
                                         "args": [to_arg(a) for a in (args or [])]}},
            {"type": "close"},
        ]
    }

    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        delay = min(2.0 ** (attempt - 1), 8.0)
        try:
            resp = requests.post(pipeline_url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = RuntimeError(
                    f"Turso query failed (HTTP {resp.status_code}): {resp.text[:200]}")
                delay = _retry_delay(attempt, resp.headers.get("Retry-After"))
            elif resp.status_code != 200:
                raise RuntimeError(
                    f"Turso query failed (HTTP {resp.status_code}): {resp.text[:200]}")
            else:
                data = resp.json()
                results = data.get("results") or []
                if not results:
                    raise RuntimeError(
                        "Turso returned no results envelope "
                        f"(payload keys: {sorted(data.keys())})")
                item = results[0]
                if item.get("type") == "error":
                    raise RuntimeError(f"Turso SQL execution error: {item.get('error')}")
                return parse_result(item)

        if attempt >= max_attempts:
            break
        print(f"[TURSO] {type(last_exc).__name__} on attempt {attempt}/{max_attempts}: "
              f"{str(last_exc)[:120]} — retry in {delay:.0f}s")
        time.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Turso request failed without a captured error")


def execute_pipeline(pipeline_url: str, auth_token: str,
                     requests_list: Optional[List[Dict[str, Any]]] = None,
                     payload: Optional[Dict[str, Any]] = None,
                     max_attempts: int = DEFAULT_MAX_ATTEMPTS,
                     timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, Any]]:
    """
    POST a v2 pipeline payload (one or more statements) and return the raw `results`.

    Pass either `requests_list` (a list of request objects) or `payload`
    (`{"requests": [...]}`) - the batch writers built one or the other.

    Behaviour mirrors execute_sql():
      * network errors and HTTP 429/5xx retry with backoff, honouring Retry-After;
      * any `{"type": "error"}` entry raises RuntimeError with the first message
        (deterministic, never retried);
      * the bearer token is redacted from response text that ends up in an exception.
    """
    if payload is not None:
        body = dict(payload)
    elif requests_list is not None:
        body = {"requests": requests_list}
    else:
        raise ValueError("execute_pipeline() needs requests_list or payload")

    reqs = body.get("requests")
    if not isinstance(reqs, list) or not reqs:
        raise ValueError("pipeline payload needs a non-empty 'requests' list")
    if not pipeline_url:
        raise ValueError("Turso pipeline_url is required")

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }

    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        delay = min(2.0 ** (attempt - 1), 8.0)
        try:
            resp = requests.post(pipeline_url, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = RuntimeError(
                    f"Turso pipeline failed (HTTP {resp.status_code}): "
                    f"{redact(resp.text, auth_token)[:200]}")
                delay = _retry_delay(attempt, resp.headers.get("Retry-After"))
            elif resp.status_code != 200:
                raise RuntimeError(
                    f"Turso pipeline failed (HTTP {resp.status_code}): "
                    f"{redact(resp.text, auth_token)[:200]}")
            else:
                data = resp.json()
                results = data.get("results") or []
                if not results:
                    raise RuntimeError(
                        "Turso pipeline returned no results "
                        f"(payload keys: {sorted(data.keys())})")
                errors = [
                    (item.get("error") or {}).get("message", "Unknown statement error")
                    for item in results
                    if item.get("type") == "error"
                ]
                if errors:
                    raise RuntimeError(
                        f"Turso SQL execution error ({len(errors)} statement(s)): "
                        f"{redact(errors[0], auth_token)}")
                return results

        if attempt >= max_attempts:
            break
        print(f"[TURSO] {type(last_exc).__name__} on attempt {attempt}/{max_attempts}: "
              f"{redact(str(last_exc), auth_token)[:120]} — retry in {delay:.0f}s")
        time.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Turso pipeline request failed without a captured error")
