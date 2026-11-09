"""ตั้งค่าส่งรายงานสต๊อกประจำวันทางอีเมล (รันครั้งเดียว ในหน้าต่าง Terminal ของคุณเอง)

- ถามอีเมลผู้ส่ง/ผู้รับ และ "รหัสผ่านแอพ" ของ Gmail (พิมพ์แล้วไม่แสดงบนจอ)
- ลองล็อกอิน Gmail ให้ก่อน ถ้ารหัสผิดจะไม่บันทึกอะไร
- บันทึกไว้ที่ %LOCALAPPDATA%\\PSAutotyre\\email_config.json (เฉพาะเครื่องนี้ ไม่ขึ้น OneDrive/GitHub)
- ส่งอีเมลทดสอบ 1 ฉบับให้ดูว่าเข้าจริง
"""
import getpass
import json
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PSAutotyre" / "email_config.json"
DEFAULT_EMAIL = "ps.autotyre04@gmail.com"


def main():
    print("=== ตั้งค่าส่งรายงานสต๊อกประจำวันทางอีเมล ===")
    print("วิธีสร้างรหัสผ่านแอพ: บัญชี Google > ความปลอดภัย > เปิด 'การยืนยันแบบ 2 ขั้นตอน' > ค้นหา 'รหัสผ่านแอป' (App passwords)")
    print("ตั้งชื่อว่า PS Autotyre แล้วกดสร้าง จะได้รหัส 16 ตัวอักษร\n")
    username = input(f"อีเมล Gmail ผู้ส่ง [กด Enter = {DEFAULT_EMAIL}]: ").strip() or DEFAULT_EMAIL
    to_raw = input(f"อีเมลผู้รับ (หลายอีเมลคั่นด้วย , ) [กด Enter = {username}]: ").strip()
    recipients = [x.strip() for x in to_raw.split(",") if x.strip()] or [username]
    password = getpass.getpass("รหัสผ่านแอพ 16 ตัว (พิมพ์/วางแล้วจะไม่แสดงบนจอ): ").replace(" ", "")
    if not password:
        print("ไม่ได้กรอกรหัสผ่าน ยกเลิก")
        return 1

    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=60) as server:
            server.login(username, password)
            msg = EmailMessage()
            msg["From"] = username
            msg["To"] = ", ".join(recipients)
            msg["Subject"] = "ทดสอบ: ตั้งค่าส่งรายงานสต๊อกประจำวัน PS Autotyre สำเร็จ"
            msg.set_content("ถ้าเห็นอีเมลฉบับนี้ แปลว่าตั้งค่าสำเร็จแล้ว\nตั้งแต่นี้ไปจะได้รับไฟล์ CSV รายการสินค้าแนบอีเมลทุกวัน 20:00 น.")
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        print("\nล็อกอิน Gmail ไม่ผ่าน — เช็คว่าเปิด 'การยืนยันแบบ 2 ขั้นตอน' แล้ว และใช้ 'รหัสผ่านแอพ' (ไม่ใช่รหัสผ่านปกติของบัญชี)")
        print("ยังไม่ได้บันทึกอะไรไว้")
        return 1
    except Exception as err:
        print(f"\nเชื่อมต่อ/ส่งอีเมลไม่สำเร็จ: {type(err).__name__}: {err}")
        print("ยังไม่ได้บันทึกอะไรไว้ (เช็คอินเทอร์เน็ตแล้วรันใหม่)")
        return 1

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(
        {"smtp_host": "smtp.gmail.com", "smtp_port": 465, "username": username, "app_password": password, "to": recipients},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nสำเร็จ! ส่งอีเมลทดสอบไปที่ {', '.join(recipients)} แล้ว (เช็คกล่องจดหมาย/สแปมด้วย)")
    print(f"บันทึกการตั้งค่าไว้ที่ {CONFIG_PATH}")
    print("ตั้งแต่นี้ไปรายงานจะส่งอัตโนมัติทุกวัน 20:00 น. — ยกเลิกได้โดยลบรหัสผ่านแอพใน Google หรือลบไฟล์ข้างบน")
    return 0


if __name__ == "__main__":
    sys.exit(main())
