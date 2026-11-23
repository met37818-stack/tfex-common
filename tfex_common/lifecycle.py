"""
Run lifecycle notifications: started / finished / failed.

Every job in this pipeline sent a message when it had something to report, and
nothing when it started, when it finished cleanly, or when it died with a traceback.
A crashed cron job was therefore invisible unless somebody opened GitHub Actions,
and a job that never started looked exactly like a job that ran fine.

This module gives the two long-running jobs (intraday collector, arbitrage scanner)
three explicit messages, one per lifecycle event:

    ▶️ <job> · เริ่มทำงาน     started, with the mode and parameters it was given
    ✅ <job> · จบงาน          finished, with exit code, duration and counters
    🚨 <job> · ล้มเหลว        failed, with the exit code, the stage, and the error

Rules:
  * three separate messages, as requested - no editing, no silent upgrade;
  * every sender returns False instead of raising: a Telegram outage must never be
    the reason a collector dies;
  * error text is sanitised before it leaves the process. requests puts the full
    request URL (bot token included) into ConnectionError messages, and these jobs
    run in public repositories;
  * nothing is sent when TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are unset.
"""
import os
import re
import time
from typing import Dict, Optional

from .report import Report, bullet
from .telegram import send_alert

# Patchable in tests; keeps the real sender out of the module namespace lookups.
_send = send_alert

_TOKEN_IN_TEXT = re.compile(r"bot\d+:[A-Za-z0-9_-]+")
_URL_IN_TEXT = re.compile(r"https?://\S+")
_MAX_ERROR_CHARS = 300


def _credentials(bot_token: Optional[str], chat_id: Optional[str]):
    token = (bot_token if bot_token is not None else os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    return token, chat


def _dispatch(text: str, bot_token: Optional[str], chat_id: Optional[str]) -> bool:
    token, chat = _credentials(bot_token, chat_id)
    if not token or not chat:
        return False
    try:
        return bool(_send(token, chat, text))
    except Exception:  # noqa: BLE001 - telemetry must never break the job
        return False


def safe_error_text(error) -> str:
    """Exception summary safe to publish: type, message, no URLs, no bot token."""
    if isinstance(error, BaseException):
        text = f"{type(error).__name__}: {error}"
    else:
        text = str(error)
    text = _TOKEN_IN_TEXT.sub("bot<redacted>", text)
    text = _URL_IN_TEXT.sub("<url>", text)
    text = " ".join(text.split())
    if len(text) > _MAX_ERROR_CHARS:
        text = text[:_MAX_ERROR_CHARS] + "…"
    return text


def _detail_lines(detail: Optional[Dict[str, object]]):
    lines = []
    for key, value in (detail or {}).items():
        if value is None or value == "":
            continue
        lines.append(bullet(f"<b>{key}</b>: <code>{value}</code>"))
    return lines


def run_started(
    job: str,
    mode: str = "",
    detail: Optional[Dict[str, object]] = None,
    *,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    started_at: Optional[float] = None,
) -> bool:
    """`▶️ job · เริ่มทำงาน`"""
    rep = Report(
        title=f"▶️ {job} · เริ่มทำงาน",
        subtitle=mode or "run",
        plan_heading=None,
        measured_heading="📋 <b>สิ่งที่สั่งรัน</b>",
        icon="",
    )
    for line in _detail_lines(detail):
        rep.add_measured(line)
    if started_at:
        rep.add_measured(bullet(f"<b>เริ่มเมื่อ</b>: <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>"))
    return _dispatch(rep.build_telegram(), bot_token, chat_id)


def run_finished(
    job: str,
    duration_s: float,
    mode: str = "",
    summary: Optional[Dict[str, object]] = None,
    exit_code: int = 0,
    *,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """`✅ job · จบงาน` - includes exit code and wall-clock duration."""
    subtitle = f"{mode + ' · ' if mode else ''}exit {exit_code} · ใช้เวลา {duration_s:.1f} วิ"
    rep = Report(title=f"✅ {job} · จบงาน", subtitle=subtitle, plan_heading=None,
                 measured_heading="📋 <b>สรุป</b>", icon="")
    for line in _detail_lines(summary):
        rep.add_measured(line)
    if not summary:
        rep.add_measured(bullet("ไม่มีตัวนับเพิ่มเติมในรอบนี้"))
    return _dispatch(rep.build_telegram(), bot_token, chat_id)


def run_failed(
    job: str,
    error,
    stage: str = "",
    duration_s: Optional[float] = None,
    exit_code: Optional[int] = None,
    mode: str = "",
    *,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """`🚨 job · ล้มเหลว` - sanitised error, stage and what to check next."""
    bits = []
    if mode:
        bits.append(mode)
    if exit_code is not None:
        bits.append(f"exit {exit_code}")
    if duration_s is not None:
        bits.append(f"ผ่านไป {duration_s:.1f} วิ")
    rep = Report(title=f"🚨 {job} · ล้มเหลว", subtitle=" · ".join(bits), plan_heading=None,
                 measured_heading="📋 <b>รายละเอียด</b>", icon="")
    if stage:
        rep.add_measured(bullet(f"<b>จุดที่ล้ม</b>: <code>{stage}</code>"))
    rep.add_measured(bullet(f"<b>Error</b>: <code>{safe_error_text(error)}</code>"))
    rep.add_watch("เปิด GitHub Actions run นี้เพื่อดู stack trace เต็ม · ถ้าเป็น network/session ให้ตรวจ credential ก่อน")
    return _dispatch(rep.build_telegram(), bot_token, chat_id)


class Lifecycle:
    """
    Small helper so a script does not repeat the try/except/else dance.

        life = Lifecycle("tfex-arb-opp", "EVENING_WORKER", enabled=not args.no_telegram)
        with life:
            do_the_work()
    """

    def __init__(self, job: str, mode: str = "", detail: Optional[Dict[str, object]] = None,
                 enabled: bool = True, bot_token: Optional[str] = None,
                 chat_id: Optional[str] = None):
        self.job = job
        self.mode = mode
        self.detail = detail
        self.enabled = enabled
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.started_at: Optional[float] = None
        self._completed = False

    def __enter__(self) -> "Lifecycle":
        self.started_at = time.time()
        if self.enabled:
            run_started(self.job, self.mode, self.detail,
                        bot_token=self.bot_token, chat_id=self.chat_id,
                        started_at=self.started_at)
        return self

    def elapsed(self) -> float:
        return (time.time() - self.started_at) if self.started_at else 0.0

    def finished(self, summary: Optional[Dict[str, object]] = None, exit_code: int = 0) -> bool:
        if not self.enabled or self._completed:
            return False
        self._completed = True
        return run_finished(self.job, self.elapsed(), self.mode, summary, exit_code,
                            bot_token=self.bot_token, chat_id=self.chat_id)

    def failed(self, error, stage: str = "", exit_code: Optional[int] = None) -> bool:
        if not self.enabled or self._completed:
            return False
        self._completed = True
        return run_failed(self.job, error, stage, self.elapsed(), exit_code, self.mode,
                          bot_token=self.bot_token, chat_id=self.chat_id)

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.finished()          # no-op when the caller already sent it
            return False
        if issubclass(exc_type, SystemExit):
            code = exc.code if isinstance(exc.code, int) else 0
            if code:
                self.failed(f"จบด้วย exit code {code}", stage="controlled abort", exit_code=code)
            else:
                self.finished(exit_code=0)
            return False
        self.failed(exc, stage="unhandled exception")
        return False
