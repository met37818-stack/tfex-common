"""
ตัวรัน `update_handoff.py --push` เป็นรอบ ๆ ระหว่างที่เครื่องเปิดอยู่

ออกแบบให้ตรงกับที่ต้องการ: "เปิดเครื่องเมื่อไรก็ทำ ถ้าไม่เปิดก็ไม่ต้องทำ"
  * เริ่มทำงานทันทีที่ล็อกอิน (ผ่าน shortcut ใน Startup folder)
  * แล้ววนซ้ำทุก N ชั่วโมง (ค่าเริ่มต้น 3) ตราบที่โปรเซสยังอยู่
  * ปิดเครื่อง / ล็อกเอาต์ -> โปรเซสตาย -> ไม่มีอะไรทำงาน ไม่มี task ค้าง

ไม่ใช้ Task Scheduler (เครื่องนี้ถูกปฏิเสธสิทธิ์) และไม่ต้อง admin
หน้าต่างถูกซ่อนโดยเรียกผ่าน pythonw.exe จากไฟล์ .vbs ใน Startup

    python scripts/handoff_refresh_loop.py --once              # รันรอบเดียว (ทดสอบ)
    python scripts/handoff_refresh_loop.py                     # วนทุก 3 ชั่วโมง
    python scripts/handoff_refresh_loop.py --interval-hours 6
    pythonw scripts/handoff_refresh_loop.py                    # เงียบ ไม่มีหน้าต่าง (ใช้จาก .vbs)

log: %LOCALAPPDATA%\\hermes\\logs\\handoff-refresh.log
"""
import argparse
import datetime
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATER = os.path.join(HERE, "update_handoff.py")
DEFAULT_LOG = os.path.join(os.path.expandvars(r"%LOCALAPPDATA%"), "hermes", "logs", "handoff-refresh.log")
BKK = datetime.timezone(datetime.timedelta(hours=7))


def log(message: str, path: str) -> None:
    stamp = datetime.datetime.now(BKK).strftime("%Y-%m-%d %H:%M:%S ICT")
    line = f"[{stamp}] {message}"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    try:
        print(line, flush=True)
    except Exception:
        pass


def run_once(log_path: str, verbose: bool = False) -> int:
    """เรียก updater หนึ่งรอบ เก็บ output ลง log (ใช้ python ตัวเดียวกับที่รัน loop)"""
    cmd = [sys.executable, UPDATER, "--push"]
    started = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=600)
    except subprocess.TimeoutExpired:
        log("หมดเวลา 600 วิ — ข้ามรอบนี้", log_path)
        return 124
    except Exception as exc:  # noqa: BLE001 - loop ต้องไม่ตาย
        log(f"เรียก updater ไม่ได้: {type(exc).__name__}: {exc}", log_path)
        return 1

    out = (proc.stdout or "").strip().splitlines()
    err = (proc.stderr or "").strip()
    tail = out[-1] if out else ""
    if proc.returncode == 0:
        if "ไม่มีอะไรเปลี่ยน" in (proc.stdout or ""):
            log("ไม่มีอะไรเปลี่ยน", log_path)
        else:
            log(f"อัปเดตแล้ว: {tail}", log_path)
    else:
        log(f"ล้มเหลว (exit {proc.returncode}): {tail or err[:200]}", log_path)
    if verbose:
        log(f"ใช้เวลา {time.time() - started:.1f} วิ", log_path)
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="วนอัปเดต HANDOFF เป็นรอบ ๆ")
    ap.add_argument("--once", action="store_true", help="รันรอบเดียวแล้วจบ (สำหรับทดสอบ)")
    ap.add_argument("--interval-hours", type=float, default=3.0, help="ระยะห่างระหว่างรอบ (ชั่วโมง)")
    ap.add_argument("--log", default=DEFAULT_LOG, help="ไฟล์ log")
    ap.add_argument("--verbose", action="store_true", help="บันทึกเวลาที่ใช้แต่ละรอบด้วย")
    args = ap.parse_args()

    log(f"เริ่ม loop (ทุก {args.interval_hours:g} ชม., pid {os.getpid()})", args.log)
    if args.once:
        return run_once(args.log, args.verbose)

    interval = max(0.25, args.interval_hours) * 3600.0
    while True:
        try:
            run_once(args.log, args.verbose)
        except KeyboardInterrupt:
            log("ถูกสั่งหยุด", args.log)
            return 0
        except Exception as exc:  # noqa: BLE001 - ห้ามหลุดออกจาก loop
            log(f"รอบนี้พัง: {type(exc).__name__}: {exc}", args.log)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
