"""
Shared Telegram report layout for the TFEX pipeline.

Both the pre-market playbook (tfex-quant-analytics) and the arbitrage alerts
(tfex-arb-opp) had grown their own message assembly: hand-rolled dividers, their own
`len(msg) > 4096` checks, and — more importantly — no structural distinction between
numbers that were measured and labels that were inferred. A reader could not tell a
settlement price from a dealer-gamma guess, and a value that was simply missing was
printed as 0.0.

This module gives every report the same contract:

    📊 <title>
    🕖 <subtitle> | ข้อมูลพร้อม N ส่วน · ยังไม่พร้อม M
    ━━━━━━━━━━━━━━━━━━━━━━
    📏 วัดได้ (ข้อมูลจริง)
    🧠 อนุมาน (มีสมมติฐาน)
    🎯 แผน
    ⏳ ยังไม่พร้อม: ...
    🔁 เปลี่ยนมุมมองเมื่อ: ...

Sections that are empty are omitted, so a report with nothing inferred does not
show an empty heading. Callers keep full control of the text (and of HTML escaping);
this module only owns order, framing, the ready/pending counters and the Telegram
length limit.
"""
from dataclasses import dataclass, field
from typing import List, Optional

TELEGRAM_LIMIT = 4096
DIVIDER = "━" * 22
TRUNCATION_NOTICE = "… <i>(ตัดข้อความ: เกินขีดจำกัด Telegram)</i>"

ICON_MEASURED = "📏"
ICON_INFERRED = "🧠"
ICON_PLAN = "🎯"
ICON_PENDING = "⏳"
ICON_WATCH = "🔁"

HEADING_MEASURED = f"{ICON_MEASURED} <b>วัดได้ (ข้อมูลจริง)</b>"
HEADING_PLAN = f"{ICON_PLAN} <b>แผน</b>"
HEADING_INFERRED = f"{ICON_INFERRED} <b>อนุมาน (มีสมมติฐาน)</b>"
HEADING_PENDING = f"{ICON_PENDING} <b>ยังไม่พร้อม:</b>"
HEADING_WATCH = f"{ICON_WATCH} <b>เปลี่ยนมุมมองเมื่อ:</b>"


def rr(target: float, entry: float, stop: float) -> str:
    """
    Structural risk/reward, direction-agnostic.

    Returns "n/a" when the levels do not bracket the entry, because a negative or
    infinite R:R printed as a number is worse than an explicit n/a.
    """
    try:
        risk = abs(float(entry) - float(stop))
        reward = abs(float(target) - float(entry))
    except (TypeError, ValueError):
        return "n/a"
    if risk <= 0 or reward <= 0:
        return "n/a"
    return f"1:{reward / risk:.1f}"


def bullet(text: str, indent: str = "  ") -> str:
    """One bullet line. Text is inserted verbatim (caller owns escaping/tags)."""
    return f"{indent}• {text}"


def sub(text: str, indent: str = "    ") -> str:
    return f"{indent}– {text}"


@dataclass
class Report:
    """Composable Telegram report with a measured / inferred / plan split."""

    title: str
    subtitle: str = ""
    measured: List[str] = field(default_factory=list)
    inferred: List[str] = field(default_factory=list)
    plan: List[str] = field(default_factory=list)
    pending: List[str] = field(default_factory=list)
    watch: List[str] = field(default_factory=list)
    footer: str = ""
    ready_sections: Optional[int] = None
    plan_heading: Optional[str] = HEADING_PLAN
    show_divider: bool = True

    # ---------------------------------------------------------------- builders
    def add_measured(self, line: str) -> "Report":
        self.measured.append(line)
        return self

    def add_inferred(self, line: str) -> "Report":
        self.inferred.append(line)
        return self

    def add_plan(self, line: str) -> "Report":
        self.plan.append(line)
        return self

    def add_pending(self, what: str) -> "Report":
        if what not in self.pending:
            self.pending.append(what)
        return self

    def add_watch(self, line: str) -> "Report":
        self.watch.append(line)
        return self

    # ---------------------------------------------------------------- metadata
    def meta_line(self) -> str:
        parts = []
        if self.subtitle:
            parts.append(self.subtitle)
        if self.ready_sections is not None:
            parts.append(f"ข้อมูลพร้อม {self.ready_sections} ส่วน")
        if self.pending:
            parts.append(f"ยังไม่พร้อม {len(self.pending)}")
        return " | ".join(parts)

    # ---------------------------------------------------------------- rendering
    def _section(self, heading: Optional[str], lines: List[str]) -> List[str]:
        if not lines:
            return []
        out = []
        if heading:
            out.append(heading)
        out.extend(lines)
        return out

    def build(self) -> str:
        """Full message. Empty sections are omitted entirely."""
        return self._render(self.measured, self.inferred)

    def _render(self, measured: List[str], inferred: List[str]) -> str:
        blocks: List[List[str]] = []

        head = [f"📊 <b>{self.title}</b>"]
        meta = self.meta_line()
        if meta:
            head.append(f"🕖 <i>{meta}</i>")
        blocks.append(head)

        if self.show_divider:
            blocks.append([DIVIDER])

        for heading, lines in (
            (HEADING_MEASURED, measured),
            (HEADING_INFERRED, inferred),
            (self.plan_heading, self.plan),
        ):
            section = self._section(heading, lines)
            if section:
                blocks.append(section)

        if self.pending:
            blocks.append([f"{HEADING_PENDING} " + " · ".join(self.pending)])
        if self.watch:
            blocks.append([f"{HEADING_WATCH} " + " · ".join(self.watch)])

        if self.show_divider:
            blocks.append([DIVIDER])
        if self.footer:
            blocks.append([self.footer])

        # Dividers hug the neighbouring block; content sections get a blank line so the
        # measured / inferred / plan split stays visually obvious in Telegram.
        blocks = [b for b in blocks if b]
        out: List[str] = []
        for i, block in enumerate(blocks):
            if i:
                tight = blocks[i - 1] == [DIVIDER] or block == [DIVIDER]
                out.append("\n" if tight else "\n\n")
            out.append("\n".join(block))
        return "".join(out)

    def build_telegram(self, limit: int = TELEGRAM_LIMIT) -> str:
        """
        Message guaranteed to fit Telegram.

        Order of sacrifice: extra measured lines, then extra inferred lines, each time
        dropping the last one. The plan, the pending list and the watch list are the
        actionable part and are kept as long as possible.
        """
        msg = self.build()
        if len(msg) <= limit:
            return msg

        measured, inferred = list(self.measured), list(self.inferred)
        while len(msg) > limit and (len(measured) > 1 or len(inferred) > 1):
            if len(measured) > 1:
                measured.pop()
            elif len(inferred) > 1:
                inferred.pop()
            msg = self._render(measured, inferred)

        if len(msg) > limit:
            keep = max(0, limit - len(TRUNCATION_NOTICE) - 1)
            msg = msg[:keep].rsplit("\n", 1)[0] + "\n" + TRUNCATION_NOTICE
        return msg
