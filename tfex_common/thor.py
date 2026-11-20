"""BOT THOR (Thai Overnight Repurchase Rate) handling.

THOR is always published as PERCENT per annum. This module refuses to guess the unit
from the magnitude, which is the exact bug that had to be fixed in four repositories:
`v / 100 if v > 0.5 else v` reads 0.45% as 45%, collapsing exp(-r*T) from 0.999630 to
0.963689 at 30 DTE and fabricating arbitrage edges of several index points.
"""
from typing import Callable, Dict, Optional, Tuple

from .constants import THOR_MAX_PCT

THOR_TENORS = ("overnight", "1m", "3m", "6m")


def to_decimal_rate(val, label: str = "") -> Optional[float]:
    """
    Convert a BOT THOR reading (percent p.a.) into a decimal annual rate.

    Returns None for missing/non-positive input, raises ValueError when the value is
    above THOR_MAX_PCT (i.e. the caller fed something that is not a percent rate).
    """
    if val is None:
        return None
    pct = float(val)
    if pct <= 0:
        return None
    if pct > THOR_MAX_PCT:
        raise ValueError(
            f"THOR rate out of range: {pct} ({label or 'unknown tenor'}) — expected percent "
            f"p.a., max {THOR_MAX_PCT}%"
        )
    return pct / 100.0


def select_dynamic_thor_rate(thor_record: Dict[str, Optional[float]],
                             dte: int) -> Tuple[float, str]:
    """
    Pick the THOR tenor matching the option's days-to-expiration.

    dte <= 30      : 1M -> ON -> 3M -> 6M
    30 < dte <= 90 : 3M -> 1M -> ON -> 6M
    90 < dte <= 180: 6M -> 3M -> 1M -> ON
    dte > 180      : 6M -> 3M -> ON -> 1M

    Returns (rate_decimal, tenor_label) and raises ValueError when every tenor is unusable.
    """
    r_on = to_decimal_rate(thor_record.get("overnight"), "overnight")
    r_1m = to_decimal_rate(thor_record.get("1m"), "1m")
    r_3m = to_decimal_rate(thor_record.get("3m"), "3m")
    r_6m = to_decimal_rate(thor_record.get("6m"), "6m")

    if dte <= 30:
        candidates = [("1M", r_1m), ("ON", r_on), ("3M", r_3m), ("6M", r_6m)]
    elif dte <= 90:
        candidates = [("3M", r_3m), ("1M", r_1m), ("ON", r_on), ("6M", r_6m)]
    elif dte <= 180:
        candidates = [("6M", r_6m), ("3M", r_3m), ("1M", r_1m), ("ON", r_on)]
    else:
        candidates = [("6M", r_6m), ("3M", r_3m), ("ON", r_on), ("1M", r_1m)]

    for label, rate in candidates:
        if rate is not None and rate > 0:
            return rate, label

    raise ValueError(f"No valid THOR rate found in record: {thor_record}")


def parse_thor_row(row) -> Dict[str, Optional[float]]:
    """Map an `eod_thor_rates` row (thor_rate, thor_1m_avg, thor_3m_avg, thor_6m_avg)."""
    if not row:
        return {tenor: None for tenor in THOR_TENORS}
    values = list(row) + [None] * 4
    return {
        "overnight": float(values[0]) if values[0] is not None else None,
        "1m": float(values[1]) if values[1] is not None else None,
        "3m": float(values[2]) if values[2] is not None else None,
        "6m": float(values[3]) if values[3] is not None else None,
    }


THOR_SQL = ("SELECT thor_rate, thor_1m_avg, thor_3m_avg, thor_6m_avg "
            "FROM eod_thor_rates ORDER BY trade_date DESC LIMIT 1;")


def fetch_thor_rates_record(execute_sql: Callable, pipeline_url: str, auth_token: str,
                            sql: str = THOR_SQL) -> Dict[str, Optional[float]]:
    """
    Fetch the latest THOR record.

    `execute_sql` is injected (usually tfex_common.turso.execute_sql) to keep this
    module free of HTTP coupling and easy to test.
    """
    _, rows = execute_sql(pipeline_url, auth_token, sql)
    if not rows:
        raise ValueError("No record found in eod_thor_rates table.")
    if rows[0] and rows[0][0] is None:
        raise ValueError("No record found in eod_thor_rates table or value is NULL.")
    return parse_thor_row(rows[0])
