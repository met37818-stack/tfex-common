"""SET calendar: contract expiry (penultimate business day) and series resolution."""
import calendar as _calendar
import datetime
import warnings
from typing import List, Tuple

from .constants import BKK_TZ, SET_HOLIDAYS

MONTH_CODES = {3: "H", 6: "M", 9: "U", 12: "Z"}
REVERSE_MONTH_CODES = {"H": 3, "M": 6, "U": 9, "Z": 12}


def get_penultimate_business_day(year: int, month: int, holidays: set = SET_HOLIDAYS) -> datetime.date:
    """
    Penultimate business day of a month — the TFEX SET50 Futures/Options expiry rule.

    Raises a warning (not an exception) when the holiday table has no data for the
    requested year: a live worker should keep running, but the date may be wrong, so
    it must be visible in the logs instead of silently wrong.
    """
    if not any(str(h).startswith(str(year)) for h in holidays):
        warnings.warn(
            f"SET_HOLIDAYS has no data for {year}: the expiry date for {year}-{month:02d} "
            f"may be wrong. Update tfex_common.constants.SET_HOLIDAYS.",
            RuntimeWarning, stacklevel=0)
        print(f"[CALENDAR] WARNING: SET_HOLIDAYS has no data for {year} — the expiry date for "
              f"{year}-{month:02d} may be wrong. Update SET_HOLIDAYS before trading that year.")

    _, last_day = _calendar.monthrange(year, month)
    biz_days = [
        datetime.date(year, month, d)
        for d in range(1, last_day + 1)
        if datetime.date(year, month, d).weekday() < 5
        and datetime.date(year, month, d).strftime("%Y-%m-%d") not in holidays
    ]
    if len(biz_days) < 2:
        return biz_days[-1] if biz_days else datetime.date(year, month, last_day)
    return biz_days[-2]


def get_contract_last_trading_day(year: int, month: int,
                                  holidays: set = SET_HOLIDAYS,
                                  tz: datetime.tzinfo = BKK_TZ) -> datetime.datetime:
    """Expiry timestamp of a quarterly contract: 16:30 ICT on the penultimate business day."""
    ltd = get_penultimate_business_day(year, month, holidays)
    return datetime.datetime(ltd.year, ltd.month, ltd.day, 16, 30, 0, tzinfo=tz)


def _split_series_code(series_code: str) -> Tuple[int, int]:
    code = str(series_code).upper().strip()
    if not code:
        raise ValueError("Empty series code")
    month = REVERSE_MONTH_CODES.get(code[0])
    if month is None:
        raise ValueError(f"Invalid series month character: '{code[0]}' (expected H, M, U or Z)")
    try:
        year_suffix = int(code[1:])
    except ValueError as exc:
        raise ValueError(f"Invalid series year suffix: '{code[1:]}'") from exc
    return month, year_suffix


def get_series_expiry_date(series_code: str, ref_date: datetime.date,
                           holidays: set = SET_HOLIDAYS) -> datetime.date:
    """
    Expiry date of a quarterly series (e.g. S50Z26 -> Dec 2026, H27 -> Mar 2027).

    The century is taken from `ref_date`, so Z26 seen in 2026 means 2026 while the
    same code seen in 2126 would mean 2126.
    """
    month, year_suffix = _split_series_code(series_code)
    year = (ref_date.year // 100) * 100 + year_suffix
    return get_penultimate_business_day(year, month, holidays)


def parse_series_expiry(series_code: str, ref_date: datetime.date,
                        holidays: set = SET_HOLIDAYS,
                        tz: datetime.tzinfo = BKK_TZ) -> datetime.datetime:
    """Same as get_series_expiry_date() but returns a 16:30 ICT aware datetime."""
    month, year_suffix = _split_series_code(series_code)
    year = (ref_date.year // 100) * 100 + year_suffix
    return get_contract_last_trading_day(year, month, holidays, tz)


def resolve_active_series_candidates(now_bkk: datetime.datetime,
                                     holidays: set = SET_HOLIDAYS) -> Tuple[List[str], str, str]:
    """
    Next four quarterly series codes plus the front and next one.

    Returns (series_list, front_series, next_series). The fallbacks ("Z26"/"H27") are
    only reachable if the holiday table is empty, and are kept for API compatibility
    with the older per-repo implementations.
    """
    candidates = []
    for year in (now_bkk.year, now_bkk.year + 1):
        for month in (3, 6, 9, 12):
            ltd = get_contract_last_trading_day(year, month, holidays)
            if ltd > now_bkk:
                candidates.append((ltd, f"{MONTH_CODES[month]}{str(year)[-2:]}"))
    candidates.sort(key=lambda item: item[0])
    series_list = [code for _, code in candidates[:4]]
    front = series_list[0] if series_list else "Z26"
    nxt = series_list[1] if len(series_list) > 1 else "H27"
    return series_list, front, nxt
