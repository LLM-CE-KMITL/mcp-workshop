# Workshop 3 · Customer Directory MCP Server

**13:00 – 13:45** (45 นาที) · เป้าหมาย: สร้าง MCP server ใหม่ของตนเอง (ไฟล์เดียว ไม่ต้องแยกแพ็กเกจ) ที่มี **tool เดียว** — `list_customers_by_segment` — สำหรับ list รายชื่อลูกค้าตาม segment ที่ป้อนเข้ามา โดยต้อง**ตรวจสอบ (validate) ค่า segment ให้อยู่ในสามค่าที่กำหนดเท่านั้นก่อนใช้งานจริง**: `"Enterprise"`, `"SME"`, `"Government"`

---

## 1. ทำไมต้องมีกิจกรรมนี้ก่อน Workshop 4

[Workshop 4](04-workshop4-mpls-noc-mcp-server.md) ที่ตามมาหลังจากนี้มีงานให้ทำพร้อมกันหลายอย่าง (tool 6 ตัว + resource + prompt) กิจกรรมสั้นๆ นี้แยกทักษะพื้นฐานที่สุดของการสร้าง MCP server ออกมาฝึกก่อนแบบเดี่ยวๆ ไม่ปนกับงานอื่น: **ประกาศ tool หนึ่งตัวให้ถูกต้อง + validate input ก่อนใช้งานจริง** ถ้าทำขั้นนี้คล่องแล้ว Workshop 4 จะเหลือแค่ทำซ้ำแพทเทิร์นเดียวกันอีกหลายรอบเท่านั้น

---

## 2. ข้อมูลตั้งต้น

ตาราง `customers` มีอยู่แล้วจริงในฐานข้อมูล (`docker/postgres/init/02_schema.sql.template:75-82`):

```sql
CREATE TABLE customers (
    customer_id  VARCHAR(16) PRIMARY KEY,
    name         TEXT        NOT NULL,
    segment      VARCHAR(16) NOT NULL,         -- Enterprise | SME | Government
    contact_email TEXT,
    CONSTRAINT customers_segment_check
        CHECK (segment IN ('Enterprise', 'SME', 'Government'))
);
```

สังเกตว่าฐานข้อมูลเองก็บังคับ (`CHECK constraint`) อยู่แล้วว่า `segment` ต้องเป็นหนึ่งในสามค่านี้เท่านั้น — แต่นั่น**ไม่ใช่เหตุผลที่จะข้ามการ validate ในโค้ดของ tool เอง** ด้วยเหตุผลสองข้อ (หลักการเดียวกับที่เรียนมาใน Module 10):

1. ข้อความ error จาก `CHECK constraint` ของ PostgreSQL (เช่น `CheckViolation`) ไม่ใช่ข้อความที่อ่านแล้วเข้าใจง่าย ต่างจาก error ที่ tool เขียนเองให้ชัดเจนว่าค่าไหนถูกต้อง
2. ถ้ารู้อยู่แล้วว่า argument ผิดตั้งแต่ต้น การส่ง query ไปให้ฐานข้อมูลปฏิเสธคือการเสีย round trip ไปฟรีๆ — หลักการเดียวกับที่ [Module 5 หัวข้อ 1.2](../day2/03-module5-react-loop.md) สอนไว้เรื่องการตรวจชื่อ tool **ก่อน**เรียก ไม่ใช่ปล่อยให้ไปพังตอนเรียกจริง

ใช้บัญชี `mcp_reader` เดิม (อ่านอย่างเดียว ตาม Module 10) เชื่อมต่อฐานข้อมูลได้เลย ไม่ต้องสร้างบัญชีใหม่

---

## 3. สิ่งที่ต้องทำ

สร้างไฟล์ `workshop3_customer_directory.py` ที่ root ของโปรเจกต์:

```python
#!/usr/bin/env python3
from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from psycopg.rows import dict_row

load_dotenv()

PG_DSN = os.getenv(
    "PG_DSN", "postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb"
)

ALLOWED_SEGMENTS = ("Enterprise", "SME", "Government")

mcp = FastMCP(name="customer-directory-workshop3")

# --- Tool ประกาศต่อจากนี้ ---

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

จากนั้นเติม tool ตัวเดียวเข้าไปแทนที่คอมเมนต์ `# --- Tool ประกาศต่อจากนี้ ---`:

```python
@mcp.tool(
    annotations={
        "title": "List customers by segment",
        "readOnlyHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
def list_customers_by_segment(segment: str) -> dict:
    """List every customer in one segment.

    Use this to answer questions like "how many Enterprise customers do we
    have" or "list all Government customers".

    Args:
        segment: exactly one of "Enterprise", "SME", "Government"
            (case-sensitive - "enterprise" or "ENTERPRISE" are rejected)
    """
    if segment not in ALLOWED_SEGMENTS:
        return {
            "ok": False,
            "error": f"segment ต้องเป็นหนึ่งใน {ALLOWED_SEGMENTS} เท่านั้น ได้รับมา: {repr(segment)}",
        }

    with psycopg.connect(PG_DSN, row_factory=dict_row) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT customer_id, name, segment, contact_email
               FROM customers WHERE segment = %s ORDER BY name""",
            (segment,),
        )
        rows = cur.fetchall()

    return {"ok": True, "segment": segment, "count": len(rows), "customers": rows}
```

**จุดสำคัญของ tool นี้**:

- การ validate อยู่**ก่อน**บรรทัดที่เชื่อมต่อฐานข้อมูลเสมอ — ถ้า `segment` ผิด ฟังก์ชันคืนค่ากลับทันทีโดยไม่แตะฐานข้อมูลเลยแม้แต่ครั้งเดียว
- คืนค่าเป็น `{"ok": False, "error": "..."}` แทนที่จะ `raise` exception ตรงๆ — เพราะ tool ที่ raise ขึ้นมาแบบไม่ได้ดักไว้อาจทำให้ client บางตัวแสดง traceback ดิบให้ผู้ใช้เห็น ในขณะที่ dict ที่คืนกลับมาแบบนี้โมเดลอ่านแล้วอธิบายต่อให้ผู้ใช้เข้าใจได้ทันที (เทียบกับแพทเทิร์น `{"found": False, ...}` ที่ `get_ticket`/`get_device_config` ใน `apps/mcp-server/tools/tickets.py` ใช้อยู่แล้ว)
- เช็คด้วย `in` กับ tuple โดยตรง (`segment not in ALLOWED_SEGMENTS`) ไม่ใช่ `.lower()` หรือ normalize ค่าก่อนเช็ค — ตั้งใจให้ต้องพิมพ์ตัวพิมพ์ใหญ่เล็กตรงตามที่กำหนดไว้ทุกประการ

---

## 4. ตัวอย่างรันได้ทันที — ทดสอบเองก่อนต่อ Claude Desktop

เรียก tool ตรงๆ ผ่าน `mcp.call_tool(...)` โดยไม่ต้องเปิด client จริง (แพทเทิร์นเดียวกับที่ Workshop 4 ใช้ตรวจสอบว่าไฟล์ประกาศ tool ถูกต้อง):

```bash
uv run python -c "
import asyncio, sys
sys.path.insert(0, '.')
import workshop3_customer_directory as w

async def main():
    tools = await w.mcp.list_tools()
    print('TOOLS:', [t.name for t in tools])

    valid = await w.mcp.call_tool('list_customers_by_segment', {'segment': 'SME'})
    print('segment=SME ->', valid[0].text[:120], '...')

    invalid = await w.mcp.call_tool('list_customers_by_segment', {'segment': 'enterprise'})
    print('segment=enterprise (พิมพ์เล็ก) ->', invalid[0].text)

asyncio.run(main())
"
```

**ผลลัพธ์จริง** (รันจริงตอนเตรียมเอกสารนี้ ด้วยเฉลย — จำนวนลูกค้าที่ได้ขึ้นกับข้อมูลจริงในฐานข้อมูล ณ ขณะรัน):

```
TOOLS: ['list_customers_by_segment']
segment=SME -> {
  "ok": true,
  "segment": "SME",
  "count": 12,
  "customers": [
    {
      "customer_id": "CUS-0020", ...
segment=enterprise (พิมพ์เล็ก) -> {
  "ok": false,
  "error": "segment ต้องเป็นหนึ่งใน ('Enterprise', 'SME', 'Government') เท่านั้น ได้รับมา: 'enterprise'"
}
```

สังเกตว่ากรณี `enterprise` (พิมพ์เล็กทั้งหมด) ถูกปฏิเสธทันที แม้จะเป็นคำที่ถูกต้องในความหมาย เพียงแต่ตัวพิมพ์ไม่ตรงตามที่กำหนดไว้ — นี่คือพฤติกรรมที่ตั้งใจออกแบบไว้ ไม่ใช่ข้อบกพร่องของโค้ด

---

## 5. ส่วนเสริม (กรณีมีเวลาเหลือ): ต่อกับ Claude Desktop จริง

ใช้ขั้นตอนเดียวกับ [Module 9 หัวข้อ 3.2](01-module9-mcp-intro.md) ทุกประการ เปลี่ยนแค่ปลายทางใน `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "customer-directory-workshop3": {
      "command": "uv",
      "args": [
        "--directory", "/absolute/path/to/MCP2",
        "run", "python", "workshop3_customer_directory.py"
      ]
    }
  }
}
```

ลองถาม *"มีลูกค้ากลุ่ม Government กี่ราย"* — ควรเรียก `list_customers_by_segment` พร้อม `segment="Government"` และลองถามคำถามที่ทำให้โมเดลอาจใส่ segment ผิดรูปแบบ (เช่น ถามถึง "ลูกค้ารายย่อย" โดยไม่บอกคำว่า SME ตรงๆ) เพื่อดูว่าโมเดลเดา mapping เองได้หรือไม่ และถ้าเดาผิดจะเห็น error message ที่ tool ส่งกลับไปจริงหรือไม่

---

## เกณฑ์ผ่าน (Definition of Done)

- [ ] `uv run python workshop3_customer_directory.py` รันได้โดยไม่มี error และค้างรอ client บน stdio
- [ ] เรียกด้วย `segment="Enterprise"`, `"SME"`, `"Government"` แล้วได้รายชื่อลูกค้าจริงจากฐานข้อมูลครบทั้งสามกลุ่ม
- [ ] เรียกด้วยค่าที่ไม่ถูกต้อง (ตัวพิมพ์ผิด เช่น `"enterprise"`, หรือค่าที่ไม่มีอยู่จริง เช่น `"VIP"`) ต้องได้ error ที่อ่านเข้าใจง่ายกลับมา **ไม่ใช่ traceback ดิบ และไม่มีการเชื่อมต่อฐานข้อมูลเกิดขึ้นเลยในกรณีนี้**
- [ ] อธิบายได้ว่าทำไมต้อง validate ในโค้ดของ tool เอง ทั้งที่ฐานข้อมูลมี `CHECK constraint` อยู่แล้ว

## สิ่งที่ต้องส่ง

ไฟล์ `workshop3_customer_directory.py` พร้อม log การรันทดสอบทั้งกรณีถูกและผิด (คัดลอกจาก terminal) — ส่งในช่องทางที่วิทยากรแจ้งไว้ต้นวัน

---

## ต่อไป

→ [Workshop 4: MPLS NOC MCP Server](04-workshop4-mpls-noc-mcp-server.md) — เอาแพทเทิร์นเดียวกันนี้ (ประกาศ tool ด้วย FastMCP + validate ก่อนใช้งานจริง) ไปทำซ้ำอีก 6 รอบ พร้อมเพิ่ม Resource และ Prompt เข้าไปด้วย
