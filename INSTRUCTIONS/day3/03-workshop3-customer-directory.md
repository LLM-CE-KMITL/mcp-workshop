# Workshop 3 · Customer Directory MCP Server

**13:00 – 13:45** (45 นาที) · เป้าหมาย: เพิ่ม **tool เดียว** — `list_customers_by_segment` — เข้าไปใน `apps/mcp-server/` ตัวจริงที่ระบบทั้งหมดใช้งานร่วมกัน สำหรับ list รายชื่อลูกค้าตาม segment ที่ป้อนเข้ามา โดยต้อง**ตรวจสอบ (validate) ค่า segment ให้อยู่ในสามค่าที่กำหนดเท่านั้นก่อนใช้งานจริง**: `"Enterprise"`, `"SME"`, `"Government"`

**ข้อแตกต่างจากกิจกรรมอื่นในหลักสูตรนี้**: ทุก Workshop ก่อนหน้านี้ (1, 2, และ Workshop 4 ที่ตามมา) ให้สร้างไฟล์แยกต่างหากของตนเอง ห้ามแก้ระบบอ้างอิง — แต่ Workshop นี้ตั้งใจให้**แก้ระบบจริงโดยตรงทั้ง `apps/mcp-server/` (เพิ่ม tool) และ `apps/agent-api/` (ขยายขอบเขตของ Intent Gate)** เพื่อฝึกความรู้สึกของการเพิ่มความสามารถเข้าไปในระบบที่ใช้งานจริงอยู่แล้ว (production-style) ถือเป็นข้อยกเว้นเฉพาะกิจกรรมนี้เท่านั้น

---

## 1. ข้อมูลตั้งต้น

ตาราง `customers` มีอยู่แล้วจริงในฐานข้อมูล ลองสำรวจข้อมูลด้วย query ต่อไปนี้ก่อนเริ่มเขียนโค้ด:

```sql
SELECT segment, count(*) FROM customers GROUP BY segment ORDER BY segment;
```

**ผลลัพธ์จริง**:

```
   segment  | count
------------+-------
 Enterprise |    10
 Government |     8
 SME        |    12
```

```sql
SELECT customer_id, name, segment, contact_email
FROM customers
WHERE segment = 'SME'
ORDER BY name
LIMIT 3;
```

**ผลลัพธ์จริง**:

```
 customer_id |             name              | segment |          contact_email
-------------+--------------------------------+---------+----------------------------------
 CUS-0020    | คลินิกกายภาพบำบัดบ้านสุขใจ      | SME     | contact20@customer.example.th
 CUS-0008    | คลินิกทันตกรรมสไมล์             | SME     | contact08@customer.example.th
 CUS-0027    | บริษัท กรีนเอเนอร์จี โซลูชั่น    | SME     | contact27@customer.example.th
```

สังเกตว่าค่าในคอลัมน์ `segment` มีเพียงสามค่านี้เท่านั้น (`Enterprise`, `SME`, `Government`) — ฐานข้อมูลเองก็บังคับไว้อยู่แล้วในระดับ schema ว่า `segment` ต้องเป็นหนึ่งในสามค่านี้เท่านั้น แต่นั่น**ไม่ใช่เหตุผลที่จะข้ามการ validate ในโค้ดของ tool เอง** ด้วยเหตุผลสองข้อ (หลักการเดียวกับที่เรียนมาใน Module 10):

1. ข้อความ error จาก `CHECK constraint` ของ PostgreSQL (เช่น `CheckViolation`) ไม่ใช่ข้อความที่อ่านแล้วเข้าใจง่าย ต่างจาก error ที่ tool เขียนเองให้ชัดเจนว่าค่าไหนถูกต้อง
2. ถ้ารู้อยู่แล้วว่า argument ผิดตั้งแต่ต้น การส่ง query ไปให้ฐานข้อมูลปฏิเสธคือการเสีย round trip ไปฟรีๆ — หลักการเดียวกับที่ [Module 5 หัวข้อ 1.2](../day2/03-module5-react-loop.md) สอนไว้เรื่องการตรวจชื่อ tool **ก่อน**เรียก ไม่ใช่ปล่อยให้ไปพังตอนเรียกจริง

ไม่ต้องต่อฐานข้อมูลเอง — ใช้ตัวช่วย `db.pg_query()` ที่มีอยู่แล้วใน `apps/mcp-server/db.py` (ต่อผ่านบัญชี `mcp_reader` อ่านอย่างเดียวเดิม ตาม Module 10 เหมือน tool อื่นทุกตัวในระบบ)

---

## 2. สิ่งที่ต้องทำ

### ขั้นที่ 1 — เพิ่มไฟล์ tool ใหม่

สร้างไฟล์ `apps/mcp-server/tools/customers.py` (ไฟล์ใหม่ ยังไม่มีอยู่ในระบบ):

```python
"""Customer directory tool (PostgreSQL)."""

from __future__ import annotations

from db import pg_query
from security import guardrails

ALLOWED_SEGMENTS = ("Enterprise", "SME", "Government")


def register(mcp) -> None:

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

        Use this to answer questions like "how many Enterprise customers do
        we have" or "list all Government customers".

        Do NOT use this to look up a single customer by name or ID - there is
        no tool for that; this one only filters by segment.

        Args:
            segment: exactly one of "Enterprise", "SME", "Government"
                (case-sensitive - "enterprise" or "ENTERPRISE" are rejected)
        """
        if segment not in ALLOWED_SEGMENTS:
            return {
                "ok": False,
                "error": f"segment ต้องเป็นหนึ่งใน {ALLOWED_SEGMENTS} เท่านั้น ได้รับมา: {repr(segment)}",
            }

        rows = pg_query(
            """SELECT customer_id, name, segment, contact_email
               FROM customers WHERE segment = %s ORDER BY name""",
            (segment,),
        )
        return guardrails.redact_deep(
            {"ok": True, "segment": segment, "count": len(rows), "customers": rows}
        )
```

โครงนี้ตรงตามแพทเทิร์นเดียวกับทุก tool ที่มีอยู่แล้วใน `apps/mcp-server/tools/tickets.py` ทุกประการ — ฟังก์ชัน `register(mcp)` ระดับโมดูล ประกาศ tool ด้วย `@mcp.tool` ข้างใน

### ขั้นที่ 2 — ลงทะเบียน tool ใน server

เปิด `apps/mcp-server/server.py` แล้วเพิ่ม 2 บรรทัด ต่อจากบรรทัดที่เพิ่ม `notifications` ไว้ก่อนหน้า (รูปแบบเดียวกันเป๊ะ):

ที่ส่วน import (ต่อจากบรรทัด `from tools import logs, network, reports, tickets, notifications  # เพิ่ม notifications ต่อท้าย`):

```python
from tools import customers  # เพิ่มบรรทัดนี้สำหรับ Workshop 3
```

ที่ในฟังก์ชัน `build_server()` (ต่อจากบรรทัด `notifications.register(mcp)  # เพิ่มบรรทัดนี้ลงไป`):

```python
customers.register(mcp)  # เพิ่มบรรทัดนี้สำหรับ Workshop 3
```

**จุดสำคัญของ tool นี้**:

- การ validate อยู่**ก่อน**บรรทัดที่เรียก `pg_query()` เสมอ — ถ้า `segment` ผิด ฟังก์ชันคืนค่ากลับทันทีโดยไม่แตะฐานข้อมูลเลยแม้แต่ครั้งเดียว
- คืนค่าเป็น `{"ok": False, "error": "..."}` แทนที่จะ `raise` exception ตรงๆ — เพราะ tool ที่ raise ขึ้นมาแบบไม่ได้ดักไว้อาจทำให้ client บางตัวแสดง traceback ดิบให้ผู้ใช้เห็น ในขณะที่ dict ที่คืนกลับมาแบบนี้โมเดลอ่านแล้วอธิบายต่อให้ผู้ใช้เข้าใจได้ทันที (เทียบกับแพทเทิร์น `{"found": False, ...}` ที่ `get_ticket`/`get_device_config` ใน `apps/mcp-server/tools/tickets.py` ใช้อยู่แล้ว)
- เช็คด้วย `in` กับ tuple โดยตรง (`segment not in ALLOWED_SEGMENTS`) ไม่ใช่ `.lower()` หรือ normalize ค่าก่อนเช็ค — ตั้งใจให้ต้องพิมพ์ตัวพิมพ์ใหญ่เล็กตรงตามที่กำหนดไว้ทุกประการ
- ห่อผลลัพธ์ด้วย `guardrails.redact_deep(...)` ก่อน return เสมอ ตามธรรมเนียมเดียวกับทุก tool อื่นในระบบ (Module 10 หัวข้อ 4) แม้ข้อมูลลูกค้าจะไม่น่ามีความลับซ่อนอยู่ก็ตาม — ทำให้เป็นนิสัยเดียวกันทุก tool ดีกว่าต้องจำว่า tool ไหนต้องห่อบ้าง

### ขั้นที่ 3 — ขยายขอบเขตของ Intent Gate (จำเป็น ไม่ใช่ตัวเลือก)

ทำถึงขั้นที่ 2 แล้วลองถามผ่าน Chainlit UI ทันที คำถามอย่าง *"ขอรายชื่อลูกค้า sme"* จะ**ถูกปฏิเสธก่อนถึง tool เลย** ด้วยข้อความ "คำถามนี้อยู่นอกขอบเขตของระบบ" — ไม่ใช่บั๊กของ tool ที่เพิ่งเขียน แต่เป็นเพราะ **Intent Gate จาก Module 7 (วันที่ 2)** ที่คั่นอยู่หน้า ReAct loop ใน `apps/agent-api/agent/intent.py` ยังไม่รู้จักความสามารถใหม่นี้เลย

`SYSTEM_PROMPT` ของ Intent Gate (`apps/agent-api/agent/intent.py:141-144`) ระบุขอบเขตของระบบไว้ตรงๆ ว่าตอบได้เรื่องอะไรบ้าง:

```
device configuration, physical topology, routing adjacencies, device logs,
equipment health, customer circuits and operational runbooks.
```

สังเกตว่ามีแค่ **"customer circuits"** (วงจรของลูกค้า) ไม่มี "รายชื่อลูกค้าตาม segment" เลย — โมเดลที่ทำหน้าที่ตัดสินใจ scope จึงมองว่าคำถามเกี่ยวกับ "รายชื่อลูกค้า" เป็นเรื่อง business/sales data ไม่ใช่เรื่องโครงข่าย แล้วปฏิเสธไปอย่างสมเหตุสมผลตามขอบเขตเดิมที่กำหนดไว้ (ทดสอบแล้วจริงตอนเตรียมเอกสารนี้ — ได้ `label: OUT_OF_SCOPE, reason: "...falls under business data or sales information, not network operations"`)

**นี่คือบทเรียนสำคัญของ Workshop นี้**: การเพิ่ม tool ใหม่เข้าไปใน MCP server อย่างเดียวไม่พอ — ถ้าระบบมี Intent Gate คั่นอยู่ด้านหน้า (แบบใน `apps/agent-api/`) ต้องขยายขอบเขตที่ Intent Gate รู้จักด้วย ไม่เช่นนั้น tool จะ "มีอยู่จริงแต่เรียกไม่ถึง" ตลอดไป

แก้ `apps/agent-api/agent/intent.py` บรรทัด 142-143 จาก:

```python
device configuration, physical topology, routing adjacencies, device logs,
equipment health, customer circuits and operational runbooks. It covers exactly
```

เป็น:

```python
device configuration, physical topology, routing adjacencies, device logs,
equipment health, customer circuits, the customer directory (listing
customers by segment: Enterprise, SME, Government) and operational runbooks.
It covers exactly
```

**ผลลัพธ์จริง** (ทดสอบเปรียบเทียบก่อน/หลังแก้ตอนเตรียมเอกสารนี้ ด้วยคำถามเดียวกัน):

```
ก่อนแก้: label=OUT_OF_SCOPE  reason="...falls under business data or sales information, not network operations"
หลังแก้: label=IN_SCOPE      reason="...covered under the customer directory in the network operations data"
```

---

## 3. ทดสอบผ่าน Chainlit UI

เรียก tool ด้วยการถามผ่าน UI ตรงๆ ไม่ต้องเขียนสคริปต์แยกและไม่ต้องตั้งค่า client ใหม่เลย — เพราะ `apps/agent-api/agent/mcp_client.py:34-40` เรียก `build_server()` จากไฟล์ `apps/mcp-server/server.py` ที่เพิ่งแก้ไปตรงๆ ทุกครั้ง (โหมด `in_process` ซึ่งเป็นค่าเริ่มต้นระหว่างทำ lab ตามคอมเมนต์ที่ `mcp_client.py:7-9`) ดังนั้นทันทีที่บันทึกไฟล์ทั้งสามในขั้นที่ 1-3 เสร็จ **agent ทั้งระบบจะเห็นและเรียก tool ใหม่นี้ได้ทันที**

เปิดสองเทอร์มินัลแยกกัน:

```bash
uv run uvicorn main:app --app-dir apps/agent-api --reload --port 8080
```

```bash
uv run chainlit run apps/chainlit-ui/app.py --port 8000 -w
```

เปิดเบราว์เซอร์ไปที่ `http://localhost:8000` แล้วถาม:

> "มีลูกค้ากลุ่ม Government กี่ราย"

**สิ่งที่ควรเห็น**: Chainlit แสดง step ของ ReAct loop (Thought → Action → Observation) ที่มีการเรียก `list_customers_by_segment` พร้อม `segment="Government"` แล้วสรุปจำนวนลูกค้าเป็นคำตอบ

จากนั้นลองถามคำถามที่กำกวมโดยตั้งใจ (เช่น *"ลูกค้ารายย่อยมีกี่ราย"* โดยไม่พูดคำว่า SME ตรงๆ) เพื่อดูว่าโมเดลเดา mapping เองได้ถูกต้องหรือไม่ — ถ้าโมเดลเดาผิด (เช่นส่ง `"small business"` หรือ `"smes"` แทนที่จะเป็น `"SME"` เป๊ะ) ต้องเห็น error message ที่ tool เขียนไว้ปรากฏใน Observation ของ step นั้นทันที ไม่ใช่ traceback หรือ agent ค้าง

---

## 4. (โบนัส) ตรวจสอบผ่าน Claude Desktop

เพราะ tool ใหม่ถูกเพิ่มเข้าไปใน `apps/mcp-server/` ตัวเดียวกับที่ [Module 9 หัวข้อ 3.2](01-module9-mcp-intro.md) ต่อกับ Claude Desktop ไว้แล้วในชื่อ `nt-network` **จึงไม่ต้องเพิ่ม entry ใหม่ใน `claude_desktop_config.json` เลย** — แค่ปิดแล้วเปิด Claude Desktop ใหม่ tool `list_customers_by_segment` จะปรากฏในรายการ tool ของ `nt-network` ทันที ลองถามคำถามเดียวกับหัวข้อ 3 เพื่อเทียบพฤติกรรมระหว่างสอง client

---

## เกณฑ์ผ่าน (Definition of Done)

- [ ] `apps/mcp-server/server.py` import และเรียก `customers.register(mcp)` แล้ว รันด้วย `uv run uvicorn main:app --app-dir apps/agent-api --reload --port 8080` ไม่มี error ตอน build server
- [ ] แก้ `apps/agent-api/agent/intent.py` ขยายขอบเขตของ Intent Gate แล้ว (ขั้นที่ 3) — คำถามเกี่ยวกับรายชื่อลูกค้าตาม segment ต้องผ่าน Intent Gate ไม่ถูกปฏิเสธว่า out_of_scope
- [ ] ถามผ่าน Chainlit UI (`uv run chainlit run apps/chainlit-ui/app.py --port 8000 -w`) ด้วย segment ทั้งสามค่าที่ถูกต้อง (`Enterprise`, `SME`, `Government`) แล้วได้รายชื่อลูกค้าจริงจากฐานข้อมูลครบทั้งสามกลุ่ม เห็นในหน้าต่าง Thought → Action → Observation
- [ ] ถามด้วยคำถามที่ทำให้โมเดลอาจส่ง segment ผิดรูปแบบ ต้องเห็น error ที่ tool เขียนเองปรากฏใน Observation **ไม่ใช่ traceback ดิบ และ agent ไม่ค้าง**
- [ ] อธิบายได้ว่าทำไมต้อง validate ในโค้ดของ tool เอง ทั้งที่ฐานข้อมูลมี `CHECK constraint` บังคับ `segment` อยู่แล้วในระดับ schema
- [ ] อธิบายได้ว่าทำไม tool ที่เขียนถูกต้องสมบูรณ์แล้วยังเรียกไม่ถึงได้ ถ้าไม่แก้ Intent Gate ตามขั้นที่ 3

## สิ่งที่ต้องส่ง

ไฟล์ `apps/mcp-server/tools/customers.py` ที่เขียนเสร็จ พร้อม diff ของ `apps/mcp-server/server.py` (2 บรรทัดที่เพิ่ม) และ `apps/agent-api/agent/intent.py` (ส่วนขอบเขตที่แก้) และภาพหน้าจอ/บันทึกข้อความจาก Chainlit UI ขณะเรียก tool สำเร็จอย่างน้อย 1 ครั้ง — ส่งในช่องทางที่วิทยากรแจ้งไว้ต้นวัน

---

## ต่อไป

→ [Workshop 4: MPLS NOC MCP Server](04-workshop4-mpls-noc-mcp-server.md) — เอาแพทเทิร์นเดียวกันนี้ (ประกาศ tool ด้วย FastMCP + validate ก่อนใช้งานจริง) ไปทำซ้ำอีก 6 รอบ พร้อมเพิ่ม Resource และ Prompt เข้าไปด้วย
