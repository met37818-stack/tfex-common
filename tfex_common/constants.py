"""Shared constants for the TFEX SET50 pipeline."""
import datetime
import os

# Thailand has no DST, so a fixed +07:00 offset is exact and avoids a pytz dependency.
BKK_TZ = datetime.timezone(datetime.timedelta(hours=7))

CONTRACT_MULTIPLIER = 200.0  # THB per SET50 index point

# Round-turn fee per leg: 2 sides x FEE_PER_SIDE_THB THB / 200 THB per point.
FEE_PER_SIDE_THB = float(os.getenv("FEE_PER_SIDE_THB", "20.0"))
COMMISSION_PER_LEG_PTS = (2.0 * FEE_PER_SIDE_THB) / CONTRACT_MULTIPLIER  # 0.20 pts
COMMISSION_2LEG_PTS = 2.0 * COMMISSION_PER_LEG_PTS                       # 0.40 pts (80 THB)
COMMISSION_3LEG_PTS = 3.0 * COMMISSION_PER_LEG_PTS                       # 0.60 pts (120 THB)
COMMISSION_4LEG_PTS = 4.0 * COMMISSION_PER_LEG_PTS                       # 0.80 pts (160 THB)

# BOT publishes THOR as PERCENT per annum (0.994 == 0.994%). Never infer the unit
# from magnitude: 0.45% read as 45% collapses exp(-r*T) and fabricates parity edges.
THOR_MAX_PCT = 25.0

# Hard clamp for dealer charm exposure when DTE <= 2 (charm asymptote guard).
CHARM_CLAMP = 5000.0

# Official SET holidays. Sourced from the SET holiday calendar; the 2026 list has 20
# days (including 2026-10-16, which was missing from tfex-quant-analytics before the
# 2026-11-22 review), 2027 has 18, 2028 has 15.
SET_HOLIDAYS = {
    # 2026
    "2026-01-01", "2026-01-02", "2026-03-03", "2026-04-06", "2026-04-13",
    "2026-04-14", "2026-04-15", "2026-05-01", "2026-05-04", "2026-06-01",
    "2026-06-03", "2026-07-28", "2026-07-29", "2026-08-12", "2026-10-13",
    "2026-10-16", "2026-10-23", "2026-12-07", "2026-12-10", "2026-12-31",
    # 2027
    "2027-01-01", "2027-02-22", "2027-04-06", "2027-04-13", "2027-04-14",
    "2027-04-15", "2027-05-03", "2027-05-04", "2027-05-20", "2027-06-03",
    "2027-07-19", "2027-07-28", "2027-08-12", "2027-10-13", "2027-10-25",
    "2027-12-06", "2027-12-10", "2027-12-31",
    # 2028
    "2028-01-03", "2028-02-10", "2028-04-06", "2028-04-13", "2028-04-14",
    "2028-05-01", "2028-05-05", "2028-06-05", "2028-07-17", "2028-07-28",
    "2028-08-14", "2028-10-13", "2028-10-23", "2028-12-05", "2028-12-11",
}
