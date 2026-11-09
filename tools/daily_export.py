"""ส่งออกรายการสินค้าทุกสาขาเป็น CSV ลงโฟลเดอร์ใน OneDrive (รันอัตโนมัติทุกวันด้วย Windows Task Scheduler)

- อ่านข้อมูลจาก Supabase อย่างเดียว (GET) ไม่เขียน/ไม่ลบอะไรในฐานข้อมูลเลย
- คอลัมน์เหมือนปุ่ม "ออกรายงาน CSV" ในหน้ารายการสินค้าของแอพ แต่ออกครบทุกรายการของแต่ละสาขา
- ดึงข้อมูลแบบแบ่งหน้า (Supabase ตัดผลลัพธ์ที่ 1,000 แถวถ้าไม่แบ่งหน้า) และเทียบกับจำนวนแถวจริงก่อนบันทึก
  ถ้าดึงไม่ครบ/ไม่ได้ จะไม่เขียนไฟล์ทับของเดิม และบันทึกสาเหตุไว้ใน export_log.txt
- ถ้าตั้งค่าอีเมลไว้แล้ว (รัน tools/setup_email.py ครั้งเดียว) จะส่งไฟล์ CSV แนบอีเมลให้ด้วยทุกวัน
  รหัสผ่านแอพอยู่ในไฟล์ในเครื่องนี้เท่านั้น (%LOCALAPPDATA%\\PSAutotyre\\email_config.json) ไม่อยู่ใน OneDrive/GitHub
"""
import csv
import json
import os
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

SUPABASE_URL = "https://ofjsvfnthrokggugynjn.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_e_pe4MUnEXPe_HYPf2Z6JQ_HWu46406"

BRANCHES = {"phrabat": "พระบาท", "lotus_pongsanuk": "โลตัสปงสนุก"}
OUT_DIR = Path.home() / "OneDrive" / "Documents" / "รายงานสต๊อกประจำวัน"
LOG_FILE = OUT_DIR / "export_log.txt"
HEADERS = ["หมวดสินค้า", "ยี่ห้อ", "รุ่น", "ขนาด", "รหัสสินค้า", "บาร์โค้ด", "ราคาซื้อ", "ราคาขาย", "คงเหลือ"]
PAGE = 1000
ATTEMPTS = 5
RETRY_WAIT_SECONDS = 30
CONFIG_PATH = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PSAutotyre" / "email_config.json"
EMAIL_ATTEMPTS = 3


def log(message):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    try:
        print(line)
    except Exception:
        pass


def request(path, extra_headers=None):
    req = urllib.request.Request(SUPABASE_URL + path, headers={
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": "Bearer " + SUPABASE_ANON_KEY,
        **(extra_headers or {}),
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8")), resp.headers.get("Content-Range", "")


def fetch_branch(branch):
    """ดึงสินค้าทั้งหมดของสาขา แบ่งหน้าครบ และตรวจจำนวนแถวกับ count จริงจากเซิร์ฟเวอร์"""
    query = (
        "/rest/v1/products?select=*&branch=eq." + urllib.parse.quote(branch)
        + "&order=category.asc,brand.asc,model.asc,size.asc,id.asc"
    )
    rows, offset, expected = [], 0, None
    while True:
        batch, content_range = request(query, {
            "Range": f"{offset}-{offset + PAGE - 1}",
            "Prefer": "count=exact",
        })
        if expected is None and "/" in content_range:
            total = content_range.split("/")[-1]
            expected = int(total) if total.isdigit() else None
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    if expected is not None and len(rows) != expected:
        raise RuntimeError(f"ดึงข้อมูลไม่ครบ: ได้ {len(rows)} แถว แต่ฐานข้อมูลมี {expected} แถว")
    if not rows:
        raise RuntimeError("ไม่ได้ข้อมูลสินค้าเลยสักแถว (ไม่เขียนไฟล์ว่างทับของเดิม)")
    return rows


def write_csv(path, rows):
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, lineterminator="\r\n")
        writer.writerow(HEADERS)
        for p in rows:
            writer.writerow([
                p.get("category") or "", p.get("brand") or "", p.get("model") or "", p.get("size") or "",
                p.get("code") or "", p.get("barcode") or "",
                p.get("costPrice") if p.get("costPrice") is not None else 0,
                p.get("sellPrice") if p.get("sellPrice") is not None else 0,
                p.get("qty") if p.get("qty") is not None else 0,
            ])
    tmp.replace(path)   # เขียนไฟล์ชั่วคราวให้เสร็จก่อนค่อยแทนที่ ไม่ทิ้งไฟล์ครึ่งๆกลางๆ


def export_branch(branch, label, stamp):
    """คืน dict สรุปผล (label, path, count, qty) ถ้าสำเร็จ / คืน {"label", "error"} ถ้าไม่สำเร็จ"""
    last_error = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            rows = fetch_branch(branch)
            path = OUT_DIR / f"รายการสินค้า_{label}_{stamp}.csv"
            write_csv(path, rows)
            total_qty = sum(int(p.get("qty") or 0) for p in rows)
            log(f"OK  สาขา{label}: {len(rows)} รายการ จำนวนรวม {total_qty} ชิ้น -> {path.name}")
            return {"label": label, "path": path, "count": len(rows), "qty": total_qty}
        except Exception as err:  # เน็ตหลุด / Supabase พักโปรเจกต์ / DNS ล้มชั่วคราว -> ลองใหม่
            last_error = err
            log(f"WARN สาขา{label} ครั้งที่ {attempt}/{ATTEMPTS} ไม่สำเร็จ: {err}")
            if attempt < ATTEMPTS:
                time.sleep(RETRY_WAIT_SECONDS)
    log(f"FAIL สาขา{label}: {last_error}")
    return {"label": label, "error": str(last_error)}


# ---------------- อีเมลรายงานประจำวัน ----------------

def load_email_config():
    if not CONFIG_PATH.exists():
        return None
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg["app_password"] = str(cfg["app_password"]).replace(" ", "")
    recipients = cfg.get("to") or [cfg["username"]]
    cfg["to"] = [recipients] if isinstance(recipients, str) else list(recipients)
    return cfg


def previous_summary(label, stamp):
    """สรุป (วันที่, จำนวนรายการ, จำนวนชิ้นรวม) จากไฟล์ CSV ของวันก่อนหน้าล่าสุด ไว้เทียบว่าเปลี่ยนไปเท่าไหร่"""
    older = sorted(p for p in OUT_DIR.glob(f"รายการสินค้า_{label}_*.csv") if p.stem.split("_")[-1] < stamp)
    if not older:
        return None
    path = older[-1]
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))[1:]
        return path.stem.split("_")[-1], len(rows), sum(int(float(r[8] or 0)) for r in rows if len(r) > 8)
    except Exception:
        return None


def build_email(cfg, stamp, results):
    failed = [r for r in results if "error" in r]
    msg = EmailMessage()
    msg["From"] = cfg["username"]
    msg["To"] = ", ".join(cfg["to"])
    msg["Subject"] = ("⚠️ ส่งออกไม่ครบ — " if failed else "") + f"รายงานสต๊อกประจำวัน PS Autotyre {stamp}"
    lines = [f"รายการสินค้าประจำวันที่ {stamp} (แนบไฟล์ CSV แยกสาขา เปิดด้วย Excel ได้เลย)", ""]
    for r in results:
        if "error" in r:
            lines.append(f"สาขา{r['label']}: ส่งออกไม่สำเร็จ — {r['error']}")
            continue
        line = f"สาขา{r['label']}: {r['count']:,} รายการ / จำนวนรวม {r['qty']:,} ชิ้น"
        prev = previous_summary(r["label"], stamp)
        if prev:
            d_items, d_qty = r["count"] - prev[1], r["qty"] - prev[2]
            line += f"  (เทียบ {prev[0]}: รายการ {d_items:+d}, จำนวน {d_qty:+d})"
        lines.append(line)
    if failed:
        lines += ["", "ดูสาเหตุเพิ่มเติมได้ที่ไฟล์ export_log.txt ในโฟลเดอร์ รายงานสต๊อกประจำวัน (OneDrive)"]
    lines += ["", "— ส่งอัตโนมัติจากเครื่องคอมที่ร้านทุกวัน 20:00 น."]
    msg.set_content("\n".join(lines))
    for r in results:
        if "path" in r:
            msg.add_attachment(r["path"].read_bytes(), maintype="text", subtype="csv", filename=r["path"].name)
    return msg


def send_email_report(stamp, results):
    """คืน True=ส่งสำเร็จ, False=ส่งไม่สำเร็จ, None=ยังไม่ได้ตั้งค่าอีเมล (ข้ามไป)"""
    try:
        cfg = load_email_config()
    except Exception as err:
        log(f"EMAIL ไฟล์ตั้งค่าอีเมลอ่านไม่ได้: {err}")
        return False
    if cfg is None:
        log("EMAIL ข้าม — ยังไม่ได้ตั้งค่าอีเมล (รัน tools/setup_email.py ครั้งเดียวเพื่อเปิดใช้)")
        return None
    msg = build_email(cfg, stamp, results)
    ctx = ssl.create_default_context()
    last_error = None
    for attempt in range(1, EMAIL_ATTEMPTS + 1):
        try:
            with smtplib.SMTP_SSL(cfg.get("smtp_host", "smtp.gmail.com"), int(cfg.get("smtp_port", 465)),
                                  context=ctx, timeout=60) as server:
                server.login(cfg["username"], cfg["app_password"])
                server.send_message(msg)
            log(f"EMAIL OK  ส่งถึง {', '.join(cfg['to'])}")
            return True
        except Exception as err:
            last_error = err
            log(f"EMAIL WARN ครั้งที่ {attempt}/{EMAIL_ATTEMPTS} ไม่สำเร็จ: {type(err).__name__}: {err}")
            if attempt < EMAIL_ATTEMPTS:
                time.sleep(20)
    log(f"EMAIL FAIL: {last_error}")
    return False


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    results = [export_branch(branch, label, stamp) for branch, label in BRANCHES.items()]
    export_ok = all("error" not in r for r in results)
    email_ok = send_email_report(stamp, results)   # ส่งแม้ส่งออกไม่ครบ เพื่อให้เจ้าของรู้ว่ามีปัญหา
    if not export_ok:
        return 1
    return 2 if email_ok is False else 0


if __name__ == "__main__":
    sys.exit(main())
