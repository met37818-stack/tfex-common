# HANDOFF — TFEX SET50 pipeline (5 repos)

> อัปเดตล่าสุด: <!-- AUTO:UPDATED -->2026-11-23 12:45 ICT<!-- /AUTO:UPDATED --> · เอกสารนี้เขียนเพื่อให้ session ใหม่ทำงานต่อได้ทันทีโดยไม่ต้องค้น history
> ที่เก็บโค้ดในเครื่อง: `$HOME/Documents/tfex-review\` · GitHub org: `met37818-stack`

---

## 1. สถานะปัจจุบัน (ตรวจจาก GitHub API ณ วันเขียน)

<!-- AUTO:STATUS:START -->
| repo | บทบาท | pin `tfex-common` | tests | CI บน main | PR ค้าง |
|---|---|---|---|---|---|
| `tfex-common` | shared lib (ใช้ร่วมทุก repo) | — (tag **v0.6.0** = `d73c2c9`) | ? | ⏳ | 0 |
| `tfex-eod-collector` | ดึง EOD จาก TFEX/BOT → Turso | `84c52f8` (v0.5.0) | **42** | ✅ | 0 |
| `tfex-intraday-collector` | เก็บ bar 1 นาทีผ่าน Settrade v2 → Turso | `d73c2c9` (v0.6.0) | **41** | ✅ | 0 |
| `tfex-arb-opp` | สแกน arbitrage จากข้อมูล intraday | `d73c2c9` (v0.6.0) | **50** | ✅ | 0 |
| `tfex-quant-analytics` | playbook เช้า + dashboard GitHub Pages | `84c52f8` (v0.5.0) | **36** | ✅ | 0 |
<!-- AUTO:STATUS:END -->

ทุก repo มี `.github/workflows/tests.yml` (pytest บน push + PR) และ step `if: failure() || cancelled()` ที่ยิง Telegram fallback

---

## 2. สถาปัตยกรรม

```
TFEX / BOT (www.tfex.co.th, app.bot.or.th)
        │  scrape + REST
        ▼
tfex-eod-collector ──► Turso (eod_* tables)  ◄── tfex-quant-analytics (playbook 06:45)
        │                                              │
        │                    ┌─────────────────────────┘
        ▼                    ▼
tfex-intraday-collector ──► Turso (spot/futures/options snapshots 1 นาที)
   (Settrade v2)                 │
                                 ▼
                        tfex-arb-opp (สแกนทุก 1 นาที + summary ท้าย session)

tfex-common = ไลบรารีกลางที่ทุกตัว import (pin เป็น commit SHA)
```

โมดูลใน `tfex_common`:

| module | ให้อะไร |
|---|---|
| `constants` | `SET_HOLIDAYS` (53 วัน), `CONTRACT_MULTIPLIER`, ค่าคอม, `THOR_MAX_PCT` |
| `calendar` | ปฏิทินเทรด, `get_penultimate_business_day`, expiry ของ series |
| `thor` | อ่าน THOR จาก BOT (percent → decimal, กัน 0.45% อ่านเป็น 45%) |
| `turso` | client v2 pipeline + retry + `execute_pipeline` (batch) + redact |
| `telegram` | `send_alert` / `send_document` (ไม่ log URL ที่มี token) + `escape_html` |
| `report` | เทมเพลตข้อความ: 📏 วัดได้ / 🧠 อนุมาน / 🎯 แผน / ⏳ ยังไม่พร้อม / 🔁 เปลี่ยนมุมมองเมื่อ + บังคับ 4096 ตัวอักษร |
| `levels` | `Level`/`LevelBook` (ladder + walls + nearest) และ `plan_leg()` (entry/stop/target/R:R) |
| `lifecycle` | `run_started` / `run_finished` / `run_failed` + `Lifecycle` context manager |

---

## 3. ตารางเวลา (trigger มาจาก **cron-job.org** ภายนอก ไม่ใช่ `on: schedule`)

| เวลา ICT | repo / workflow | ทำอะไร |
|---|---|---|
| 06:45 ทุกวัน | `tfex-quant-analytics` → `Pre-Market Quant Radar` | สร้าง playbook + dashboard แล้วส่ง Telegram |
| 06:15 ทุกวัน | `tfex-eod-collector` → `Stateless EOD Data Collector` | **gate ตัวจริง** ของ EOD (strict: ข้อมูลไม่ครบ = exit 3) |
| 01:15 ทุกวัน | eod เดียวกัน | early tick (tolerant ผ่าน `--allow-stale` ถ้า TFEX ยังไม่ลง) |
| 21:15 ทุกวัน | eod เดียวกัน | warm-up tick (tolerant) |
| 09:15, 14:00 | `tfex-intraday-collector` → `Collect TFEX 1-Minute Data` | session worker เก็บ bar (timeout 240 นาที) |
| 09:40, 14:10 | `tfex-arb-opp` → `TFEX Real-time 1-Minute Arbitrage Radar` | worker สแกน arb + summary ท้าย session |

**window ที่ eod ยอมรับข้อมูลเก่า**: 14:00–18:00 UTC = 21:00–02:00 ICT (`collect_eod.yml`) — 06:15 ICT (23:00 UTC) อยู่นอก window จึง strict

---

## 4. Telegram: อะไรแจ้งอะไร (สำคัญ)

| repo | เหตุการณ์ | ข้อความ | เงื่อนไข/หมายเหตุ |
|---|---|---|---|
| **eod** | EOD สำเร็จ | `📊 TFEX & BOT EOD Collection Complete` (ผล + THOR + storage + retention) | ส่งเฉพาะ **05:30–07:30 ICT** หรือ `--notify` (กัน duplicate) |
| eod | TFEX ยังไม่ลงข้อมูล (stale) | `📊 EOD collector stopped: data not published yet` | `notify_stale_refusal()` ก่อน `exit 3` |
| eod | exit 4 (options ว่าง) / crash / timeout | runner-failure step | ไม่มีข้อความระดับแอป — ใช้ fallback ของ runner |
| **intraday** | เริ่ม / จบ / ล้ม | `▶️` / `✅` / `🚨` (แยก 3 ข้อความ) | `Lifecycle` — รวมถึง **exit 3 ตลาดนิ่ง = 🚨** |
| intraday | checkpoint 09:45 / 12:30 / 13:45 / 16:55 | `📊 TFEX INTRADAY · …` | ข้ามถ้าไม่มีข้อมูลวันนั้น (Data Guard) |
| intraday | exception กลาง session | `🚨 CRITICAL FAILURE` | cooldown 15 นาที |
| **arb** | เริ่ม / จบ / ล้ม | `▶️` / `✅` / `🚨` | `--no-telegram` ปิดทั้ง 3 |
| arb | พบโอกาส | `🚨 LIVE ARB ALERT` | cooldown 15 นาที/คู่สัญญา + สมมติฐาน fill + เงื่อนไขยกเลิก |
| arb | ท้าย session | summary + ไฟล์ `.xlsx` | |
| arb | Turso ไม่มีข้อมูล | `[ABORT]` | |
| **quant** | playbook รายวัน | `🎯 แผนการเทรด SET50` | ไม่มีข้อความระดับแอปเมื่อล้ม (มี runner fallback) |
| ทุก repo | timeout / cancelled / crash ก่อน entry point | `🚨 <workflow>` (runner step) | curl ล้วน ทำงานได้แม้ pip install ล้ม |

---

## 5. กติกาการทำงาน (ที่ตกลงกันไว้)

1. **ห้าม merge PR เอง** — เจ้าของ repo เป็นผู้อนุมัติ/merge ทุกครั้ง (ผู้ช่วยเปิด PR แล้วหยุด)
2. **pin `tfex-common` เป็น commit SHA** ไม่ใช่ tag (tag ย้ายได้) — อยู่ใน `requirements.txt` และ `requirements-dev.txt`
3. **รายงานรีวิวเป็นภาษาไทย** แบ่ง Critical / Warning / Suggestion พร้อม `path:line` จากไฟล์จริง
4. **ห้ามแต่งผลทดสอบ** — mock ไม่นับเป็น end-to-end; ถ้าทำไม่ได้ให้บอกตรง ๆ
5. **ทุกคำตอบปิดท้ายด้วย “ผมต้องทำอะไรบ้าง”** (ขั้นตอนที่ผู้ใช้ต้องลงมือเอง)
6. ข้อความ Telegram ต้องแยก **วัดได้ / อนุมาน / ยังไม่พร้อม** และไม่พิมพ์ `0.0` แทนข้อมูลที่ไม่มี

---

## 6. คำสั่งตรวจสุขภาพ (ก็อปวางได้)

```bash
# 1) PR ค้างทุก repo
GH="$LOCALAPPDATA/gh/gh.exe"
for r in tfex-eod-collector tfex-intraday-collector tfex-arb-opp tfex-quant-analytics tfex-common; do
  echo "== $r =="; "$GH" pr list --repo "met37818-stack/$r" --state open
done

# 2) CI ล่าสุดบน main
for r in tfex-eod-collector tfex-intraday-collector tfex-arb-opp tfex-quant-analytics tfex-common; do
  "$GH" run list --repo "met37818-stack/$r" --branch main --limit 1 \
    --json name,conclusion,createdAt --jq '.[0]'
done

# 3) เทสต์ในเครื่อง (ใช้ venv ที่มีอยู่)
cd $HOME/Documents/tfex-review/tfex-eod-collector      && $LOCALAPPDATA/Temp/tfex-repo1-311/.venv/Scripts/python.exe -m pytest -q
cd $HOME/Documents/tfex-review/tfex-intraday-collector && $LOCALAPPDATA/Temp/repo2-311/.venv/Scripts/python.exe -m pytest -q
cd $HOME/Documents/tfex-review/tfex-arb-opp            && .venv311/Scripts/python.exe -m pytest -q
cd $HOME/Documents/tfex-review/tfex-quant-analytics    && .venv/Scripts/python.exe -m pytest -q
cd $HOME/Documents/tfex-review/tfex-common             && .venv311/Scripts/python.exe -m pytest -q

# 4) ตรวจว่า pin ติดตั้งได้จริงจาก SHA
pip install --force-reinstall --no-deps "tfex-common @ git+https://github.com/met37818-stack/tfex-common.git@<sha>"

# 5) ตรวจ TFEX ปล่อยข้อมูลวันไหนล่าสุด (ไม่ต้องมี credential)
#    ต้อง warm-up cookie ก่อน และต้องส่ง Referer ไม่งั้นได้ 403
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
REF="https://www.tfex.co.th/en/market-data/historical-data/trading-statistics-by-series"
JAR="$LOCALAPPDATA/Temp/tfex.jar"          # native curl ไม่เข้าใจ path แบบ /tmp ของ MSYS
curl -s -c "$JAR" -o NUL "$REF" -H "User-Agent: $UA"
curl -s -b "$JAR" "https://www.tfex.co.th/api/set/tfex/series/S50Z26/historical-trading?website=tfex&lang=en" \
  -H "User-Agent: $UA" -H "Referer: $REF" | head -c 300

# 6) playbook smoke (ไม่ต้องต่อ Turso)
cd $HOME/Documents/tfex-review/tfex-quant-analytics && .venv/Scripts/python.exe pre_market_radar.py --test --no-telegram
```

---

### อัปเดตสถานะอัตโนมัติ

```bash
cd "$HOME/Documents/tfex-review/tfex-common"
python scripts/update_handoff.py --check    # ดูว่าจะเปลี่ยนอะไร (ไม่เขียนไฟล์)
python scripts/update_handoff.py            # เขียนหัวข้อ 1 + 9 + เวลาอัปเดตให้ตรง GitHub
python scripts/update_handoff.py --no-tests # โหมดเร็ว: ข้ามการดึงจำนวนเทสต์จาก CI log
```

สคริปต์ (`scripts/update_handoff.py`) อ่าน/เขียนเฉพาะบล็อกระหว่าง `<!-- AUTO:… -->` — ถ้า marker หายจะหยุดแทนที่จะเขียนทับทั้งไฟล์
ใช้ `gh` CLI ที่ login ไว้ (หรือตั้ง `GH_BIN` ชี้ไปที่ gh.exe)

## 7. ข้อจำกัด / หนี้ทางเทคนิคที่รู้อยู่

| เรื่อง | สถานะ |
|---|---|
| เครื่องนี้ไม่มี credential ของ Turso / Settrade | รัน end-to-end กับ DB จริงไม่ได้ — ตรวจได้แค่ unit test + ตีกับ TFEX API จริง |
| `eod-collector` + `quant-analytics` ยัง pin v0.5.0 | ไม่พัง (ไม่ใช้ `lifecycle`) แต่ถ้าอยากให้ตรงกันทั้ง 5 → bump เป็น `d73c2c9` |
| `eod` success alert ส่งเฉพาะ 05:30–07:30 ICT | ตั้งใจกัน duplicate → รอบ 21:15 / 01:15 ที่สำเร็จจะเงียบ |
| `intraday --notify` ไม่มี lifecycle | ตั้งใจ (คำสั่งนี้คือการส่งข้อความอยู่แล้ว) |
| `quant` ไม่มีข้อความระดับแอปเมื่อล้ม | มี runner-failure step แทน |
| TFEX ลงข้อมูลเป็นรอบ (investor types/THOR มาก่อน settlement) | ต้นเหตุ exit 3 ตอน 01:15 — ไม่ใช่บั๊ก |
| vision model ของ Hermes ตาย (404) | ห้ามใช้ตรวจภาพ; ยืนยันด้วย API แทน |
| `curl` (native) ไม่เข้าใจ path `/tmp` ของ MSYS | ต้องใช้ `C:/Users/...` — ไม่งั้นเจอ "client returned ERROR on write" |

---

## 8. เริ่ม session ใหม่ยังไง

ไม่ต้อง setup อะไร — เปิดมาแล้วสั่งได้เลย ตัวอย่างคำสั่ง:

- `"ตรวจ 5 repo ว่ายังเขียวไหม"` → ไล่ `gh pr list` + CI
- `"ดูข้อความ Telegram รอบเช้านี้"` → ตรวจ log/ผลรัน
- `"รีวิว repo X"` → ใช้ skill `code-review` (ไทย 3 ระดับ)
- `"bump pin เป็น <sha>"` → อัปเดต `requirements*.txt` + PR

สิ่งที่ผมจำได้ข้าม session: ไฟล์นี้, `MEMORY.md` (facts ของเครื่อง/repo), `USER.md` (สไตล์), skills
สิ่งที่ผมจำไม่ได้: บทสนทนายาว ๆ — ถ้าต้องการบริบทเก่า ให้บอกหัวข้อ ผมจะค้นด้วย `session_search`

---

## 9. ประวัติ tag ของ `tfex-common`

<!-- AUTO:TAGS:START -->
| tag | sha | เพิ่มอะไร |
|---|---|---|
| v0.1.0 | `cef3573` | แยก helper ออกจาก 4 repo (รอบแรก) |
| v0.1.1 | `66abc0d` | รับ futures symbol เต็มรูป + ตรวจ quarter code |
| v0.2.0 | `8b3aa1c` | แยก helper ออกมา (calendar / THOR / Turso / Telegram) |
| v0.3.0 | `e4c52ec` | `execute_pipeline()` (batch), `normalize_url`, redact token |
| v0.4.0 | `5159e7a` | `report` — เทมเพลต วัดได้/อนุมาน/แผน + limit 4096 |
| v0.5.0 | `84c52f8` | `levels` — `Level`, `LevelBook`, `plan_leg` |
| v0.6.0 | `d73c2c9` | `lifecycle` — `▶️ / ✅ / 🚨` สำหรับงานที่รันนาน |
<!-- AUTO:TAGS:END -->
> ทุก tag ชี้ commit ที่ repo ลูกข่าย pin ไว้ — ถ้า PR ถัดไปถูกแก้จน commit เปลี่ยน ต้อง re-tag ให้ตรง
