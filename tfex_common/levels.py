"""
Price levels and plan legs for trading messages.

The playbook, the arb alerts and anything else that talks about strikes end up
formatting the same three things: an ordered ladder of levels with open interest,
the options walls, and a plan leg with entry / stop / targets and a risk-reward
figure. Each repository had its own copy of that formatting, which is how one of
them printed a bare "(1,085)" next to a strike — a number with no unit or meaning
attached.

Rules encoded here:
  * every level carries its OI with the label "OI", never a bare parenthetical;
  * a missing level is omitted, not printed as 0;
  * risk-reward comes from tfex_common.report.rr(), so a level that does not
    bracket the entry reports "n/a" instead of a meaningless ratio;
  * direction is explicit (stop below for long, above for short), because the two
    legs of the same plan used to be formatted by two different code paths.
"""
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple, Union

from .report import rr


def _price(value: float, digits: int = 0) -> str:
    return f"<code>{value:.{digits}f}</code>"


@dataclass
class Level:
    """One price level, optionally with the open interest sitting on it."""

    price: float
    oi: Optional[int] = None
    label: str = ""
    digits: int = 0

    def render(self) -> str:
        if self.oi is None:
            return _price(self.price, self.digits)
        return f"{_price(self.price, self.digits)} (OI {self.oi:,})"


@dataclass
class LevelBook:
    """
    The four tactical levels plus the option walls and max pain.

    All fields except the four tactical levels are optional, so a caller that only
    knows the ladder can still use the object.
    """

    res2: Level
    res1: Level
    sup1: Level
    sup2: Level
    put_wall: Optional[float] = None
    call_wall: Optional[float] = None
    max_pain: Optional[float] = None

    def ladder_line(self) -> str:
        """`ต้าน 2 1010 (OI 1,085) | ต้าน 1 1000 (OI 983) | รับ 1 980 (OI 1,602) | รับ 2 970 (OI 1,479)`"""
        parts = [
            f"ต้าน 2 {self.res2.render()}",
            f"ต้าน 1 {self.res1.render()}",
            f"รับ 1 {self.sup1.render()}",
            f"รับ 2 {self.sup2.render()}",
        ]
        return " | ".join(parts)

    def walls_line(self) -> str:
        """`Put Wall 960 | Call Wall 1100 | Max Pain 1020` - missing values are skipped."""
        parts: List[str] = []
        if self.put_wall is not None:
            parts.append(f"Put Wall {_price(self.put_wall)}")
        if self.call_wall is not None:
            parts.append(f"Call Wall {_price(self.call_wall)}")
        if self.max_pain is not None:
            parts.append(f"Max Pain {_price(self.max_pain)}")
        return " | ".join(parts)

    def levels(self) -> List[Level]:
        return [self.sup2, self.sup1, self.res1, self.res2]

    def nearest(self, price: float) -> Tuple[str, Level]:
        """Nearest tactical level to `price`, with its side."""
        candidates = [
            ("รับ 2", self.sup2), ("รับ 1", self.sup1),
            ("ต้าน 1", self.res1), ("ต้าน 2", self.res2),
        ]
        label, level = min(candidates, key=lambda item: abs(item[1].price - price))
        return label, level


Target = Union[float, Tuple[float, str]]


def _target_parts(target: Target) -> Tuple[float, str]:
    if isinstance(target, (tuple, list)):
        price, note = target[0], target[1] if len(target) > 1 else ""
        return float(price), str(note)
    return float(target), ""


def plan_leg(
    side: str,
    entry_lo: float,
    entry_hi: float,
    stop: float,
    targets: Sequence[Target],
    style: str = "เข้า",
    emoji: str = "",
    entry_digits: int = 1,
    stop_digits: int = 0,
) -> str:
    """
    One plan leg: entry zone, stop, every target with its risk-reward.

    `side` is "long" or "short" and only decides which way the stop is stated; the
    R:R itself is direction-agnostic.
    """
    is_long = side.lower().startswith("l")
    stop_op = "&lt;" if is_long else "&gt;"
    entry_lo, entry_hi = min(entry_lo, entry_hi), max(entry_lo, entry_hi)
    entry_ref = entry_hi if is_long else entry_lo

    head = f"{emoji + ' ' if emoji else ''}<b>{side.capitalize()}</b> | {style} " \
           f"{_price(entry_lo, entry_digits)}–{_price(entry_hi, entry_digits)}"
    stop_part = f"Stop Loss {stop_op}{_price(stop, stop_digits)}"

    target_parts: List[str] = []
    for index, raw in enumerate(targets):
        price, note = _target_parts(raw)
        ratio = rr(target=price, entry=entry_ref, stop=stop)
        prefix = "เป้า " if index == 0 else ""
        piece = f"{prefix}{_price(price)} (R:R {ratio})"
        if note:
            piece += f" {note}"
        target_parts.append(piece)

    body = " | ".join([head, stop_part])
    if target_parts:
        body += " | " + " → ".join(target_parts)
    return body
