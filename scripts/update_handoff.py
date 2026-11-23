"""
อัปเดต HANDOFF.md ให้ตรงกับสถานะจริงบน GitHub

    python scripts/update_handoff.py            # เขียน docs/HANDOFF.md (ค่าเริ่มต้น)
    python scripts/update_handoff.py --check    # แค่บอกว่าจะเปลี่ยนอะไร ไม่เขียนไฟล์
    python scripts/update_handoff.py --no-tests # ข้ามการดึงจำนวนเทสต์จาก CI (เร็ว)

ดึงจาก GitHub ผ่าน gh CLI (ใช้ credential ที่ login ไว้แล้ว):
  * pin ของ tfex-common ใน requirements.txt บน main ของแต่ละ repo
  * จำนวน PR ที่เปิดอยู่
  * ผล CI ล่าสุดบน main + จำนวนเทสต์ที่ผ่าน (อ่านจาก log ของ run)
  * รายการ tag ของ tfex-common พร้อม sha

เขียนเฉพาะบล็อกระหว่าง marker ในไฟล์:
    <!-- AUTO:STATUS:START --> ... <!-- AUTO:STATUS:END -->
    <!-- AUTO:TAGS:START -->   ... <!-- AUTO:TAGS:END -->
    <!-- AUTO:UPDATED --> ... <!-- /AUTO:UPDATED -->
ส่วนอื่นของเอกสารไม่ถูกแตะ ถ้า marker หาย สคริปต์จะหยุดแทนที่จะเขียนทับทั้งไฟล์

หมายเหตุ: ไฟล์ทั้งหมดเป็น UTF-8 และไฟล์ต้นทางใช้ CRLF — สคริปต์รักษา line ending เดิมไว้
"""
import argparse
import base64
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

OWNER = "met37818-stack"
BKK = datetime.timezone(datetime.timedelta(hours=7))

# repo → บทบาทที่ใช้ในตาราง (ต้องตรงกับหัวข้อ 1)
REPOS: List[Tuple[str, str]] = [
    ("tfex-common", "shared lib (ใช้ร่วมทุก repo)"),
    ("tfex-eod-collector", "ดึง EOD จาก TFEX/BOT → Turso"),
    ("tfex-intraday-collector", "เก็บ bar 1 นาทีผ่าน Settrade v2 → Turso"),
    ("tfex-arb-opp", "สแกน arbitrage จากข้อมูล intraday"),
    ("tfex-quant-analytics", "playbook เช้า + dashboard GitHub Pages"),
]

# คำอธิบายภาษาไทยที่ตั้งใจเขียนไว้ — ใช้แทน annotation ของ tag ถ้ามี
CURATED_TAGS = {
    "v0.1.0": "แยก helper ออกจาก 4 repo (รอบแรก)",
    "v0.1.1": "รับ futures symbol เต็มรูป + ตรวจ quarter code",
    "v0.2.0": "แยก helper ออกมา (calendar / THOR / Turso / Telegram)",
    "v0.3.0": "`execute_pipeline()` (batch), `normalize_url`, redact token",
    "v0.4.0": "`report` — เทมเพลต วัดได้/อนุมาน/แผน + limit 4096",
    "v0.5.0": "`levels` — `Level`, `LevelBook`, `plan_leg`",
    "v0.6.0": "`lifecycle` — `▶️ / ✅ / 🚨` สำหรับงานที่รันนาน",
}

STATUS_RE = re.compile(r"(<!-- AUTO:STATUS:START -->\n)(.*?)(\n<!-- AUTO:STATUS:END -->)", re.S)
TAGS_RE = re.compile(r"(<!-- AUTO:TAGS:START -->\n)(.*?)(\n<!-- AUTO:TAGS:END -->)", re.S)
UPDATED_RE = re.compile(r"(<!-- AUTO:UPDATED -->)(.*?)(<!-- /AUTO:UPDATED -->)")
PASSED_RE = re.compile(r"(\d+) passed")


# --------------------------------------------------------------------------- gh
def gh_bin() -> str:
    env = os.environ.get("GH_BIN")
    if env and os.path.exists(env):
        return env
    found = shutil.which("gh")
    if found:
        return found
    default = os.path.expandvars(r"%LOCALAPPDATA%\gh\gh.exe")
    if os.path.exists(default):
        return default
    sys.exit("ไม่พบ gh CLI — ตั้ง GH_BIN หรือติดตั้ง gh ก่อน (winget install GitHub.cli)")


def gh(args: List[str], quiet: bool = True) -> str:
    proc = subprocess.run([gh_bin()] + args, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        if not quiet:
            sys.stderr.write(proc.stderr[-500:])
        return ""
    return proc.stdout.strip()


def gh_json(args: List[str]):
    out = gh(args)
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


# ------------------------------------------------------------------- collectors
def pin_of(repo: str) -> str:
    """commit ที่ pin อยู่ใน requirements.txt บน main ('' ถ้าไม่มี)"""
    raw = gh([c for c in [
        "api", f"repos/{OWNER}/{repo}/contents/requirements.txt?ref=main", "--jq", ".content"
    ]])
    if not raw:
        return ""
    try:
        text = base64.b64decode(raw).decode("utf-8", "ignore")
    except Exception:
        return ""
    for line in text.splitlines():
        if "tfex-common" in line and "@" in line:
            return line.rsplit("@", 1)[1].strip()
    return ""


def open_prs(repo: str) -> int:
    data = gh_json(["pr", "list", "--repo", f"{OWNER}/{repo}", "--state", "open", "--json", "number"])
    return len(data or [])


def latest_main_run(repo: str) -> Dict[str, str]:
    data = gh_json(["run", "list", "--repo", f"{OWNER}/{repo}", "--branch", "main",
                    "--limit", "1", "--json", "databaseId,conclusion,status,createdAt,name"])
    return (data or [{}])[0]


def passed_count(repo: str, run_id) -> Optional[int]:
    if not run_id:
        return None
    log = gh(["run", "view", str(run_id), "--repo", f"{OWNER}/{repo}", "--log"])
    hits = PASSED_RE.findall(log or "")
    return int(hits[-1]) if hits else None


def tags_of(repo: str) -> List[Tuple[str, str, str]]:
    """[(tag, short_sha, subject)] เรียงตามชื่อแบบ version"""
    refs = gh_json(["api", f"repos/{OWNER}/{repo}/git/refs/tags"]) or []
    out = []
    for ref in refs:
        name = ref["ref"].split("/", 2)[-1]
        obj = ref.get("object", {})
        sha = obj.get("sha", "")
        subject = ""
        if obj.get("type") == "tag":
            tag_obj = gh_json(["api", f"repos/{OWNER}/{repo}/git/tags/{sha}"])
            if tag_obj:
                sha = (tag_obj.get("object") or {}).get("sha", sha)
                subject = (tag_obj.get("message") or "").splitlines()[0] if tag_obj.get("message") else ""
        out.append((name, sha[:7], subject))

    def key(item):
        parts = re.findall(r"\d+", item[0])
        return tuple(int(p) for p in parts) if parts else (0,)

    return sorted(out, key=key)


# ---------------------------------------------------------------------- render
def ci_cell(run: Dict[str, str]) -> str:
    status, conclusion = run.get("status", ""), run.get("conclusion")
    if status and status != "completed":
        return "⏳"
    return {"success": "✅", "failure": "❌", "cancelled": "⚪"}.get(conclusion or "", "—")


def build_status_block(rows: List[dict]) -> str:
    lines = [
        "| repo | บทบาท | pin `tfex-common` | tests | CI บน main | PR ค้าง |",
        "|---|---|---|---|---|---|",
    ]
    total_tests = 0
    for row in rows:
        pin = "—"
        if row["pin"]:
            tag = row.get("pin_tag") or ""
            pin = f"`{row['pin']}`" + (f" ({tag})" if tag else "")
        elif row["repo"] == "tfex-common":
            pin = f"— (tag **{row['latest_tag']}** = `{row['latest_tag_sha']}`)" if row["latest_tag"] else "—"
        tests = f"**{row['tests']}**" if row["tests"] is not None else "?"
        total_tests += row["tests"] or 0
        lines.append(
            f"| `{row['repo']}` | {row['role']} | {pin} | {tests} | {row['ci']} | {row['prs']} |"
        )
    # ไม่พิมพ์ยอดรวมถ้ามี repo ที่ยังไม่รู้จำนวน (โหมด --no-tests) — ตัวเลขปลอมแย่กว่าไม่มี
    if all(row["tests"] is not None for row in rows):
        lines.append("")
        lines.append(f"**รวม {total_tests} tests**")
    return "\n".join(lines)


def build_tags_block(tags: List[Tuple[str, str, str]]) -> str:
    if not tags:
        return "| tag | sha | เพิ่มอะไร |\n|---|---|---|"
    lines = ["| tag | sha | เพิ่มอะไร |", "|---|---|---|"]
    for name, sha, subject in tags:
        note = CURATED_TAGS.get(name) or subject or "—"
        lines.append(f"| {name} | `{sha}` | {note} |")
    return "\n".join(lines)


def resolve_pin_tag(pin: str, tags: List[Tuple[str, str, str]]) -> str:
    for name, sha, _ in tags:
        if sha == pin:
            return name
    return ""


def default_doc_path() -> str:
    """หา HANDOFF.md: docs/ ก่อน แล้วค่อยข้างสคริปต์ แล้วค่อยราก repo"""
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in (os.path.join(here, "..", "docs", "HANDOFF.md"),
                os.path.join(here, "..", "HANDOFF.md"),
                os.path.join(here, "HANDOFF.md")):
        if os.path.exists(rel):
            return os.path.normpath(rel)
    return os.path.normpath(os.path.join(here, "..", "docs", "HANDOFF.md"))


# ------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description="อัปเดตบล็อกสถานะใน HANDOFF.md จาก GitHub")
    ap.add_argument("--file", default="", help="path ของ HANDOFF.md (ค่าเริ่มต้น: docs/HANDOFF.md ใน repo นี้)")
    ap.add_argument("--check", action="store_true", help="ไม่เขียนไฟล์ แค่รายงานว่าจะเปลี่ยนอะไร")
    ap.add_argument("--no-tests", action="store_true", help="ข้ามการดึงจำนวนเทสต์จาก CI log")
    args = ap.parse_args()

    path = args.file or default_doc_path()
    if not os.path.exists(path):
        sys.exit(f"ไม่พบไฟล์: {path}")

    with open(path, encoding="utf-8", newline="") as fh:
        original = fh.read()
    crlf = "\r\n" in original
    doc = original.replace("\r\n", "\n")

    if not (STATUS_RE.search(doc) and TAGS_RE.search(doc) and UPDATED_RE.search(doc)):
        sys.exit("ไม่พบ marker AUTO ในไฟล์ — เพิ่ม marker ก่อน (จะได้ไม่เขียนทับทั้งเอกสาร)")

    tags = tags_of("tfex-common")
    latest_tag = tags[-1] if tags else ("", "", "")

    rows = []
    for repo, role in REPOS:
        run = latest_main_run(repo)
        pin = pin_of(repo) if repo != "tfex-common" else ""
        rows.append({
            "repo": repo,
            "role": role,
            "pin": pin,
            "pin_tag": resolve_pin_tag(pin, tags) if pin else "",
            "latest_tag": latest_tag[0],
            "latest_tag_sha": latest_tag[1],
            "tests": None if args.no_tests else passed_count(repo, run.get("databaseId")),
            "ci": ci_cell(run),
            "prs": open_prs(repo),
        })
        print(f"  {repo:<26} pin={pin or '-':<8} tests={rows[-1]['tests']} ci={rows[-1]['ci']} prs={rows[-1]['prs']}")

    status_block = build_status_block(rows)
    tags_block = build_tags_block(tags)

    # อัปเดตเนื้อหาก่อน แล้วค่อยแตะ timestamp เฉพาะเมื่อมีอะไรเปลี่ยนจริง
    # (ไม่งั้นทุก run จะเขียนไฟล์ใหม่เพราะเวลาขยับ -> diff รก)
    new_doc = STATUS_RE.sub(lambda m: m.group(1) + status_block + m.group(3), doc, count=1)
    new_doc = TAGS_RE.sub(lambda m: m.group(1) + tags_block + m.group(3), new_doc, count=1)

    if new_doc == doc:
        print("ไม่มีอะไรเปลี่ยน")
        return 0

    updated = datetime.datetime.now(BKK).strftime("%Y-%m-%d %H:%M ICT")
    new_doc = UPDATED_RE.sub(lambda m: m.group(1) + updated + m.group(3), new_doc, count=1)

    if args.check:
        import difflib
        for line in list(difflib.unified_diff(doc.splitlines(), new_doc.splitlines(),
                                              "ก่อน", "หลัง", lineterm=""))[:60]:
            print(line)
        print("\n(--check: ไม่ได้เขียนไฟล์)")
        return 0

    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_doc.replace("\n", "\r\n") if crlf else new_doc)
    print(f"อัปเดตแล้ว: {path} ({updated})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
