"""Telegram dispatch with token-safe logging.

The bot token lives in the request URL, and `requests` embeds the full URL in
ConnectionError/Timeout messages. Logging `{e}` — which all four repositories did —
therefore writes the token into CI logs, and two of those repositories are public.

Rules enforced here:
  * never log a raw exception message from requests;
  * never log the request URL;
  * return False instead of raising, so a Telegram outage does not abort a job that
    has already written its results to the database.
"""
import re
from typing import Optional

import requests

DEFAULT_TIMEOUT = 25

_TAG_PATTERN = r"</?(?:b|i|code|pre|a)(?:\s+[^>]+)?>"


def escape_html(text: str) -> str:
    """
    Escape text for Telegram's HTML parse mode while keeping the supported tags.

    Supported tags are tokenised first, then stray &, < and > are escaped, then the
    tokens are restored — so `<code>a < b</code>` still renders as code with `a < b`.
    """
    if text is None:
        return ""
    placeholder = {}

    def _keep(match):
        token = f"___TG_TAG_{len(placeholder)}___"
        placeholder[token] = match.group(0)
        return token

    tokenized = re.sub(_TAG_PATTERN, _keep, str(text), flags=re.IGNORECASE)
    tokenized = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;)", "&amp;", tokenized)
    tokenized = tokenized.replace("<", "&lt;").replace(">", "&gt;")
    for token, original in placeholder.items():
        tokenized = tokenized.replace(token, original)
    return tokenized


def _api(bot_token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{bot_token}/{method}"


def send_alert(bot_token: str, chat_id: str, message_html: str,
               timeout: int = DEFAULT_TIMEOUT,
               escape: bool = False) -> bool:
    """
    Send an HTML message. Returns True on success, False on any failure.

    `escape=True` runs the text through escape_html() first; leave it False when the
    caller already produced trusted HTML (all current callers do).
    """
    if not bot_token or not chat_id:
        print("[TELEGRAM] Missing bot token or chat id — dispatch skipped.")
        return False

    text = escape_html(message_html) if escape else message_html
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(_api(bot_token, "sendMessage"), json=payload, timeout=timeout)
    except Exception as exc:  # never log the raw message: it contains the URL + token
        print(f"[TELEGRAM] sendMessage raised {type(exc).__name__} (URL/token redacted)")
        return False

    if resp.status_code != 200:
        print(f"[TELEGRAM] sendMessage failed ({resp.status_code}): {resp.text[:200]}")
        return False
    print("[TELEGRAM] Message delivered successfully.")
    return True


def send_document(bot_token: str, chat_id: str, file_bytes: bytes, filename: str,
                  caption: Optional[str] = None,
                  content_type: str = "application/vnd.openxmlformats-officedocument."
                                      "spreadsheetml.sheet",
                  timeout: int = DEFAULT_TIMEOUT) -> bool:
    """Send a file attachment (e.g. the Settrade multiple-order .xlsx)."""
    if not bot_token or not chat_id:
        print("[TELEGRAM] Missing bot token or chat id — document skipped.")
        return False

    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "HTML"
    files = {"document": (filename, file_bytes, content_type)}
    try:
        resp = requests.post(_api(bot_token, "sendDocument"), data=data, files=files,
                             timeout=timeout)
    except Exception as exc:
        print(f"[TELEGRAM] sendDocument raised {type(exc).__name__} (URL/token redacted)")
        return False

    if resp.status_code != 200:
        print(f"[TELEGRAM] sendDocument failed ({resp.status_code}): {resp.text[:200]}")
        return False
    print(f"[TELEGRAM] Document '{filename}' delivered successfully.")
    return True
