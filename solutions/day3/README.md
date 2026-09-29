# เฉลยวันที่ 3

> ⚠️ อ่านก่อนลอง = เสียโอกาสเรียนรู้ · ดูวิธีใช้ที่ [../README.md](../README.md)

`apps/mcp-server/` คือระบบ MCP Server ที่ทำงานสมบูรณ์อยู่แล้ว ใช้เป็นเฉลยอ้างอิงของ Workshop 3 — **แต่ไม่ใช่สิ่งที่ต้องแก้ไขโดยตรง** งานจริงของ Workshop 3 คือเขียนไฟล์ `workshop3_mcp_server.py` ของตนเองที่ root ของโปรเจกต์แยกต่างหาก ซึ่งเฉลยของไฟล์นั้นอยู่ที่ [`workshop3_mcp_server.py`](workshop3_mcp_server.py) ในโฟลเดอร์นี้

| กิจกรรม | เฉลยอยู่ที่ |
|---|---|
| [Module 9: MCP คืออะไร](../../INSTRUCTIONS/day3/01-module9-mcp-intro.md) | `apps/mcp-server/` (สาธิตโดยวิทยากร) |
| [Module 10: ความปลอดภัยพื้นฐาน](../../INSTRUCTIONS/day3/02-module10-security-basics.md) | `apps/mcp-server/security/guardrails.py`, `docker/postgres/init/99_readonly_role.sql` |
| [Workshop 3: MPLS NOC MCP Server](../../INSTRUCTIONS/day3/03-workshop3-mpls-noc-mcp-server.md) | [`workshop3_mcp_server.py`](workshop3_mcp_server.py) |

---

## วิธีรัน

```bash
uv run python -c "
import ast
ast.parse(open('solutions/day3/workshop3_mcp_server.py').read())
print('syntax OK')
"
```

เปิดใช้งานจริงผ่าน MCP Inspector หรือ Claude Desktop ตามขั้นตอนใน [Workshop 3](../../INSTRUCTIONS/day3/03-workshop3-mpls-noc-mcp-server.md) — ตัวไฟล์เองรอ client มาเชื่อมต่อผ่าน stdio (`mcp.run(transport="stdio")`) จึงไม่มี output ให้ดูจากการรันตรงๆ ด้วยตัวเอง

---

## `workshop3_mcp_server.py` มีอะไรบ้าง

| ส่วนประกอบ | จำนวน | มาจากไหน |
|---|---|---|
| `@mcp.tool` | 6 ตัว | logic คัดลอกจาก `solutions/day2/workshop2_agent.py` (5 ตัวแรก) และ `solutions/day2/workshop2_noc_agent.py` (`search_docs_semantic`) |
| `@mcp.resource` | 1 ตัว (`schema://noc`) | เขียนใหม่ตามแบบ `apps/mcp-server/resources/schemas.py` โดยเป็น dict คงที่ ไม่ query สดจากฐานข้อมูล |
| `@mcp.prompt` | 1 ตัว (`diagnose_shared_upstream`) | เวอร์ชันย่อของ `apps/mcp-server/prompts/templates.py` ที่ตัดขั้นตอนที่พึ่ง tool ซึ่งไม่ได้สร้างในวันนี้ออก |

ยืนยันแล้วว่าเรียก `mcp.list_tools()`/`list_resources()`/`list_prompts()` ได้ผลลัพธ์ครบ 6/1/1 ตามที่ออกแบบไว้ และตรรกะภายในของแต่ละ tool ทำงานได้จริงกับ Postgres/Neo4j/OpenSearch/MailHog ที่รันอยู่จริง (ไม่ใช่ mock)

---

## 5 จุดที่ควรอ่านเมื่อเทียบผลงาน

### 1. `security/guardrails.py` — ชั้นป้องกันที่ prompt injection ไม่สามารถเอาชนะได้

```python
def assert_read_only(query: str, tool: str) -> None:
```

ฟังก์ชันนี้รันแม้ในกรณีที่บัญชีฐานข้อมูลเป็น read-only อยู่แล้ว — ถือเป็น defence in depth
บัญชีปกป้องข้อมูล ส่วนฟังก์ชันนี้ปกป้องกรณีที่มีการตั้งค่าผิดพลาดในอนาคต และสร้าง audit log ที่อ่านแล้วเข้าใจได้ง่าย

**บั๊กจริงที่พบตอนเขียน test**: `\bpassword\b` ไม่ match `PG_PASSWORD` เพราะขีดล่างเป็น word character — ทำให้รหัสผ่านอาจรั่วไหลไปกับผลลัพธ์ของ tool ได้ ดูวิธีแก้ที่ `_SECRET_NAME`

### 2. `clock.py` — "ตอนนี้" มาจากข้อมูล ไม่ใช่นาฬิกา

```python
def data_now(refresh: bool = False) -> datetime:
```

และ tool รับเฉพาะช่วงเวลาสัมพัทธ์ (`last_7d`) ไม่รับวันที่ absolute
เพราะ **วันที่ใดก็ตามที่โมเดลคำนวณขึ้นเอง คือวันที่ที่มีโอกาสผิดพลาดได้เสมอ**

### 3. `tools/network.py` → `get_upstream_devices` — คำนวณให้ ไม่ใช่ให้โมเดลคิด

Tool นี้ไม่ได้คืนแค่ path แต่หา intersection ให้โดยตรง พร้อมฟิลด์ `interpretation` ในรูปแบบภาษาที่มนุษย์เข้าใจได้ง่าย

> **หลักการทั่วไป**: งานที่สามารถเขียนเป็นโค้ดได้อย่างแน่นอน ไม่ควรปล่อยให้โมเดลเป็นผู้ดำเนินการ

### 4. `tools/reports.py` — allowlist ไม่ใช่ deny-list

```python
ALLOWED_SCRIPTS: dict[str, dict] = {...}
subprocess.run(argv, shell=False, timeout=30)
```

"ชื่อสคริปต์" ต้องเป็นชุดปิดที่นักพัฒนากำหนด ไม่ใช่ string ที่โมเดลส่งมา
และ `shell=False` เสมอ — `shell=True` คือการเปิดช่องให้ประกอบคำสั่งใหม่

### 5. `resources/schemas.py` — ทำไม schema เป็น Resource ไม่ใช่ Tool

โมเดลควร**อ่านก่อนเริ่มคิด** ไม่ใช่ต้องตัดสินใจว่าจะเรียกหรือไม่

ผลที่วัดได้: โมเดลที่อ่าน schema แล้วจะไม่เดาชื่อ column และไม่สร้างตารางที่ไม่มีอยู่จริงขึ้นมาเอง

---

## ตรวจงานตัวเอง

```bash
make test -- tests/test_mcp_tools.py
```

```bash
make eval
```
