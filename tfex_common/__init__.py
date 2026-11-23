"""
tfex_common — shared helpers for the TFEX SET50 pipeline.

Extracted after four separate repositories were found carrying copies of the same
five helpers (Turso client, BOT THOR rate selection, SET holiday calendar, contract
expiry, Telegram dispatch). The same bugs had to be fixed four times:

* THOR was read as "percent if > 0.5 else already decimal", which turned 0.45% into
  45% and corrupted every discount factor and solved IV.
* SET_HOLIDAYS diverged between repositories (19 vs 20 holidays for 2026), so two
  repos disagreed on expiry dates.
* Telegram exception messages were logged verbatim; requests embeds the request URL
  (with the bot token) in ConnectionError/Timeout messages, leaking it into public
  CI logs.
* The Turso client raised IndexError on an unexpected envelope and never retried
  transient 5xx responses.

Every module here is deliberately dependency-light (stdlib + requests) so it can be
installed by a collector, an analytics job or a GitHub Action without dragging in
pandas/numpy.

Layout:
    tfex_common.constants   THOR_MAX_PCT, CONTRACT_MULTIPLIER, commissions, SET_HOLIDAYS
    tfex_common.calendar    penultimate business day, contract expiry, active series
    tfex_common.thor        BOT THOR unit handling and DTE-based tenor selection
    tfex_common.turso       Turso v2 pipeline client with retry/backoff
    tfex_common.telegram    redaction-safe Telegram dispatch
    tfex_common.report      measured / inferred / plan report layout + Telegram limit
"""
from .constants import (
    BKK_TZ,
    CHARM_CLAMP,
    COMMISSION_2LEG_PTS,
    COMMISSION_3LEG_PTS,
    COMMISSION_4LEG_PTS,
    COMMISSION_PER_LEG_PTS,
    CONTRACT_MULTIPLIER,
    FEE_PER_SIDE_THB,
    SET_HOLIDAYS,
    THOR_MAX_PCT,
)
from .calendar import (
    MONTH_CODES,
    REVERSE_MONTH_CODES,
    get_contract_last_trading_day,
    get_penultimate_business_day,
    get_series_expiry_date,
    is_trading_day,
    parse_series_expiry,
    resolve_active_series_candidates,
)
from .thor import (
    fetch_thor_rates_record,
    select_dynamic_thor_rate,
    to_decimal_rate,
)
from .turso import (
    execute_pipeline,
    execute_sql,
    normalize_url,
    parse_result,
    redact,
    to_arg,
)
from .report import (
    DIVIDER,
    TELEGRAM_LIMIT,
    Report,
    bullet,
    rr,
    sub,
)
from .telegram import escape_html, send_alert, send_document

__version__ = "0.4.0"

__all__ = [
    "BKK_TZ", "CHARM_CLAMP", "COMMISSION_2LEG_PTS", "COMMISSION_3LEG_PTS",
    "COMMISSION_4LEG_PTS", "COMMISSION_PER_LEG_PTS", "CONTRACT_MULTIPLIER",
    "FEE_PER_SIDE_THB", "SET_HOLIDAYS", "THOR_MAX_PCT",
    "MONTH_CODES", "REVERSE_MONTH_CODES", "get_contract_last_trading_day",
    "get_penultimate_business_day", "get_series_expiry_date", "is_trading_day",
    "parse_series_expiry",
    "resolve_active_series_candidates",
    "fetch_thor_rates_record", "select_dynamic_thor_rate", "to_decimal_rate",
    "execute_pipeline", "execute_sql", "normalize_url", "parse_result", "redact", "to_arg",
    "escape_html", "send_alert", "send_document",
    "Report", "TELEGRAM_LIMIT", "DIVIDER", "bullet", "sub", "rr",
    "__version__",
]
