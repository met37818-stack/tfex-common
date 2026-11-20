# tfex-common

Shared helpers for the TFEX SET50 pipeline (`eod-collector`, `intraday-collector`,
`arb-opp`, `quant-analytics`). Single source of truth for the code that was copied
into four repositories and had to be fixed four times.

| module | what it replaces |
|---|---|
| `tfex_common.thor` | `select_dynamic_thor_rate` / `_clean` in 4 repos |
| `tfex_common.calendar` | `SET_HOLIDAYS`, `get_penultimate_business_day`, `get_series_expiry_date` in 4 repos |
| `tfex_common.turso` | `execute_turso_sql` (+ `normalize_turso_url`, `to_turso_arg`) in 4 repos |
| `tfex_common.telegram` | `send_telegram_alert` / `send_telegram_document` in 3 repos |
| `tfex_common.constants` | `CONTRACT_MULTIPLIER`, commission hurdles, `THOR_MAX_PCT`, `BKK_TZ` |

## What was actually broken (and is now locked by tests)

* **THOR unit** — `v / 100 if v > 0.5 else v` read 0.45% as 45%. With that rate inside
  Black-76, `exp(-r*T)` collapsed from 0.999630 to 0.963689 at 30 DTE (fabricating up to
  5.2 index points of parity edge) and solved IV moved 18.00% → 24.23% on an ITM call.
  Now: always percent, bounded by `THOR_MAX_PCT = 25.0`, `ValueError` beyond that.
* **Holiday table drift** — one repo had 19 holidays for 2026 (missing `2026-10-16`)
  while three had 20, so two repos could disagree on an expiry date. Now: one table,
  with a warning when a year outside it is queried.
* **Token leak on Telegram failure** — `requests` embeds the request URL (which
  contains the bot token) in `ConnectionError`/`Timeout`. Two of the consuming repos
  are public, so logging `{e}` published the token. Now: only `type(exc).__name__`,
  and failures return `False` instead of aborting a job that already wrote its results.
* **Turso** — `data["results"][0]` raised `IndexError` on an odd envelope, and a single
  transient 5xx killed the run. Now: retry network/429/5xx with backoff honouring
  `Retry-After`, never retry deterministic SQL errors.

## Install

Pin a tag so a fix cannot reach production silently:

```bash
pip install "tfex-common @ git+https://github.com/met37818-stack/tfex-common.git@v0.2.0"
```

Add to `requirements.txt`:

```
tfex-common @ git+https://github.com/met37818-stack/tfex-common.git@v0.2.0
```

## Usage

```python
from tfex_common import (
    BKK_TZ, COMMISSION_3LEG_PTS, THOR_MAX_PCT,
    execute_sql, normalize_url, fetch_thor_rates_record,
    select_dynamic_thor_rate, get_series_expiry_date, parse_series_expiry,
    resolve_active_series_candidates, send_alert,
)

pipeline = normalize_url(os.environ["TURSO_DATABASE_URL"])
thor = fetch_thor_rates_record(execute_sql, pipeline, os.environ["TURSO_AUTH_TOKEN"])
rate, tenor = select_dynamic_thor_rate(thor, dte=30)
_, front, nxt = resolve_active_series_candidates(datetime.datetime.now(BKK_TZ))
send_alert(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"], html)
```

## Tests

```bash
pip install -e ".[test]"
python -m pytest -q
```

## Versioning

Semantic-ish: `0.x` while the API can still change. Bump the tag and update the
`@vX.Y.Z` pin in each consuming repo — never point a production workflow at `main`.

## Migration map (verified by parity runs against the live code)

| repo | helper to delete | replacement |
|---|---|---|
| `tfex-eod-collector` | `calendar_utils.py` (`SET_HOLIDAYS`, `get_penultimate_business_day`, `get_series_expiry_date`, `is_trading_day`) | `tfex_common.calendar` |
| `tfex-intraday-collector` | `SET_HOLIDAYS`, `get_penultimate_business_day`, `check_holiday_early_exit` (uses the first two) | `tfex_common.calendar` |
| `tfex-arb-opp` | `SET_HOLIDAYS`, `get_penultimate_business_day`, `get_contract_last_trading_day`, `parse_series_expiry`, `resolve_active_series_candidates`, `select_dynamic_thor_rate`, `_to_decimal_rate`, `execute_turso_sql`, `send_telegram_alert`, `send_telegram_document` | `tfex_common.{calendar,thor,turso,telegram}` |
| `tfex-quant-analytics` | same set as `arb-opp` plus `get_series_expiry_date` | `tfex_common.{calendar,thor,turso,telegram}` |

Parity measured before publishing (every case compared against the already-fixed
repo code, zero mismatches):

* `tfex-quant-analytics` — 124/124 checks (THOR across 7 rates × 8 DTEs, 36
  penultimate-business-day cases, 15 `S50Z26`/`Z26` expiry cases)
* `tfex-arb-opp` — 76/76 checks (THOR, `parse_series_expiry` as aware datetime,
  active-series resolution across three roll dates)
* `tfex-eod-collector` — 37/37 checks for 2026–2027 (its table only covered two
  years; the 2028 rows are additions, see below)

### Holiday-table superset

`tfex-eod-collector` and `tfex-intraday-collector` ship 38 holidays (2026–2027);
this package ships 53 (2026–2028). Every date in the smaller tables is present here,
and all three tables agree on 2026 (20 days) and 2027 (18 days) — adopting the
package therefore also gives those two repos 2028 coverage they currently lack.

### Differences that are deliberate, not accidental

* `get_series_expiry_date()` accepts both `Z26` and `S50Z26`; an unknown quarter
  character raises. `tfex-quant-analytics` used `code_map.get(char, 12)`, which
  silently produced a December expiry for a typo.
* `get_penultimate_business_day()` warns when the year is outside the table instead
  of returning a plausible-looking wrong date without a trace.
* THOR above `THOR_MAX_PCT` raises instead of being divided and used.

