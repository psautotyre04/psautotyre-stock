"""ส่งออกรายการสินค้าทุกสาขาเป็น CSV ลงโฟลเดอร์ใน OneDrive (รันอัตโนมัติทุกวันด้วย Windows Task Scheduler)

- อ่านข้อมูลจาก Supabase อย่างเดียว (GET) ไม่เขียน/ไม่ลบอะไรในฐานข้อมูลเลย
- คอลัมน์เหมือนปุ่ม "ออกรายงาน CSV" ในหน้ารายการสินค้าของแอพ แต่ออกครบทุกรายการของแต่ละสาขา
- ดึงข้อมูลแบบแบ่งหน้า (Supabase ตัดผลลัพธ์ที่ 1,000 แถวถ้าไม่แบ่งหน้า) และเทียบกับจำนวนแถวจริงก่อนบันทึก
  ถ้าดึงไม่ครบ/ไม่ได้ จะไม่เขียนไฟล์ทับของเดิม และบันทึกสาเหตุไว้ใน export_log.txt
"""
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
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
    last_error = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            rows = fetch_branch(branch)
            path = OUT_DIR / f"รายการสินค้า_{label}_{stamp}.csv"
            write_csv(path, rows)
            total_qty = sum(int(p.get("qty") or 0) for p in rows)
            log(f"OK  สาขา{label}: {len(rows)} รายการ จำนวนรวม {total_qty} ชิ้น -> {path.name}")
            return True
        except Exception as err:  # เน็ตหลุด / Supabase พักโปรเจกต์ / DNS ล้มชั่วคราว -> ลองใหม่
            last_error = err
            log(f"WARN สาขา{label} ครั้งที่ {attempt}/{ATTEMPTS} ไม่สำเร็จ: {err}")
            if attempt < ATTEMPTS:
                time.sleep(RETRY_WAIT_SECONDS)
    log(f"FAIL สาขา{label}: {last_error}")
    return False


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    results = [export_branch(branch, label, stamp) for branch, label in BRANCHES.items()]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
