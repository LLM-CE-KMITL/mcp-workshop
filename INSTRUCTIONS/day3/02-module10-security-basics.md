# Module 10 · ความปลอดภัยพื้นฐาน

**10:45 – 12:00** (75 นาที) · เป้าหมาย: เข้าใจว่าเหตุใด guardrail ที่เขียนไว้ใน prompt เป็นเพียงคำขอ ในขณะที่ guardrail ที่บังคับในสิทธิ์ฐานข้อมูลและในโค้ดเป็นกฎที่บังคับใช้จริง ผ่านสามกลไกที่ใช้งานอยู่แล้วใน `apps/mcp-server/`: user ฐานข้อมูลแบบอ่านอย่างเดียว, ไฟล์ `.env`, และการตัดข้อมูลลับก่อนส่งผลลัพธ์ให้โมเดล

---

## 1. หลักการตั้งต้น

คอมเมนต์เปิดของ `apps/mcp-server/security/guardrails.py:1-4` สรุปบทเรียนของโมดูลนี้ไว้ในสองประโยค:

> *"a guardrail written in a prompt is a request. A guardrail written in code is a rule."*

ไฟล์เดียวกันนี้ระบุ 5 ชั้นการป้องกันไว้ (`guardrails.py:6-12`), เรียงจากชั้นนอกสุด:

| ชั้น | กลไก | คุมอะไร |
|---|---|---|
| 1 | Read-only database roles | ฐานข้อมูลปฏิเสธคำสั่งเขียนเอง แม้บัญชีจะถูกหลอกให้ลอง |
| 2 | Query shape validation | ปฏิเสธคำสั่งอันตรายก่อนส่งออกไปด้วยซ้ำ |
| 3 | Result caps | จำนวนแถวและขนาดผลลัพธ์มีเพดาน |
| 4 | Secret redaction | ข้อความที่หน้าตาเหมือนรหัสผ่าน/token จะไม่หลุดออกไป |
| 5 | Audit log | ทุกการปฏิเสธถูกบันทึกไว้ตรวจสอบย้อนหลังได้ |

หัวข้อนี้ (Module 10) ลงลึกเฉพาะสามกลไกที่ผู้เรียนต้องนำไปใช้เองในบ่ายนี้: **ชั้น 1** (read-only user), การจัดการความลับด้วย **`.env`** (พื้นฐานที่ทำให้ชั้น 1 และชั้นอื่นทำงานได้จริง), และ **ชั้น 4** (การตัด secret ก่อนส่งให้โมเดล) ส่วนชั้น 2, 3 และ 5 เห็นผลได้จากการอ่านโค้ดเดียวกันนี้ แต่ไม่ใช่จุดเน้นของกิจกรรมภาคบ่าย

หมายเหตุสำคัญที่ปิดท้ายไฟล์นี้ (`guardrails.py:14-16`): การถอดชั้นใดชั้นหนึ่งออกไปเพียงชั้นเดียว ระบบควรยังคงปลอดภัยอยู่ — นี่คือคุณสมบัติที่ทำให้เรียกว่า "defence in depth" ไม่ใช่การป้องกันแบบจุดเดียว

---

## 2. ชั้น 1 — User ฐานข้อมูลแบบอ่านอย่างเดียว

ไฟล์ `docker/postgres/init/99_readonly_role.sql` คือชั้นป้องกันที่สำคัญที่สุดในเวิร์กช็อปทั้งหมด ตามคอมเมนต์เปิดไฟล์ (`99_readonly_role.sql:4-9`):

> *"even if a prompt injection convinces the model to issue a DELETE, the database itself refuses. Guardrails in prompts are advisory; guardrails in the permission layer are enforced."*

ขั้นตอนที่ SQL นี้ทำจริง:

```sql
EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), ro_user);
EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', ro_user);
EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', ro_user);
EXECUTE format('GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', ro_user);
```
*(`docker/postgres/init/99_readonly_role.sql:21-24`)*

สังเกตว่าไม่มี `INSERT`, `UPDATE`, `DELETE` ปรากฏในรายการ `GRANT` เลยแม้แต่บรรทัดเดียว — บัญชี `mcp_reader` จึงทำสิ่งเหล่านั้นไม่ได้ในระดับฐานข้อมูล ไม่ว่าโค้ดฝั่ง MCP server หรือ prompt injection จะพยายามสั่งอย่างไรก็ตาม นอกจากนี้ยังมีการป้องกัน query ที่ทำงานค้าง:

```sql
ALTER ROLE mcp_reader SET statement_timeout = '15s';
ALTER ROLE mcp_reader SET idle_in_transaction_session_timeout = '30s';
```
*(`docker/postgres/init/99_readonly_role.sql:39-40`)*

ทำให้ query ที่โมเดลสร้างขึ้นแล้ววนไม่รู้จบไม่สามารถยึด connection ไว้ตลอดไปได้

**ตัวอย่างรันได้ทันที** — ลองสั่ง `DELETE` ตรงๆ ด้วยบัญชี `mcp_reader` เอง (ไม่ผ่าน MCP server หรือโมเดลเลย) เพื่อพิสูจน์ว่าฐานข้อมูลปฏิเสธเองจริงๆ ไม่ใช่แค่โค้ดฝั่ง server ที่ปฏิเสธ:

```bash
uv run python -c "
import psycopg
dsn = 'postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb'
with psycopg.connect(dsn) as conn:
    cur = conn.cursor()
    try:
        cur.execute(\"DELETE FROM tickets WHERE ticket_id = 'TK-25-00005'\")
        print('ลบสำเร็จ (ไม่ควรเกิดขึ้น)')
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}')
"
```

**ผลลัพธ์จริง** (รันจริงตอนเตรียมเอกสารนี้):

```
InsufficientPrivilege: permission denied for table tickets
```

สังเกตว่า error นี้มาจาก PostgreSQL เอง (`InsufficientPrivilege`) ไม่ใช่ exception ที่โค้ด Python จงใจ raise ขึ้นมา — ต่อให้ไม่มีโค้ด Python สักบรรทัดเดียวมาดักไว้ก่อน คำสั่ง `DELETE` นี้ก็จะถูกปฏิเสธอยู่ดี นี่คือความหมายของ "guardrail ที่บังคับในสิทธิ์ฐานข้อมูลเป็นกฎที่บังคับใช้จริง" ตามหัวข้อ 1

---

## 3. ไฟล์ `.env` — แยกความลับออกจากโค้ด

`apps/mcp-server/config.py:31-34` ตั้งค่า default ของ `PG_DSN` ไว้ให้ใช้บัญชี `mcp_reader` อยู่แล้วตั้งแต่ต้น:

```python
pg_dsn: str = Field(
    default="postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb",
    alias="PG_DSN",
)
```

และคอมเมนต์ใน `.env.example:36` ย้ำกฎนี้ตรง ๆ:

```
# Read-only user. The MCP server must use ONLY this account.
PG_READONLY_USER=mcp_reader
PG_READONLY_PASSWORD=mcp_reader_password
PG_DSN=postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb
```
*(`.env.example:36-39`)*

สังเกตว่า `.env.example` ยังมี `PG_USER`/`PG_PASSWORD` อีกคู่หนึ่ง (บรรทัด 34-35) ซึ่งเป็นบัญชีที่มีสิทธิ์เขียนได้ — ใช้เฉพาะตอน seed ข้อมูลหรือรัน migration เท่านั้น MCP server ไม่เคยแตะบัญชีนั้นเลย เพราะ `config.py` อ่านเฉพาะ `PG_DSN` (ที่ผูกกับ `mcp_reader`) เข้าไปใช้งานจริง

ส่วน `MCP_SERVER_NAME`, `MCP_TRANSPORT`, `MCP_MAX_ROWS`, `MCP_MAX_LOG_RESULTS`, `MCP_QUERY_TIMEOUT_SECONDS` (`.env.example:58-66`) คือค่าที่ควบคุมชั้น 3 (result caps) — ตัวเลขเหล่านี้ไม่ได้ hardcode ไว้ในโค้ด แต่อ่านจาก `.env` ทั้งหมด ทำให้ปรับเพดานได้โดยไม่ต้องแก้โค้ดแม้แต่บรรทัดเดียว

**กฎที่ต้องถือปฏิบัติเองตลอดเวิร์กช็อปนี้**: `.env` ไม่ถูก commit เข้า git (`.gitignore:1` — `.env`) มีเพียง `.env.example` ที่เป็นแม่แบบปลอดภัยเท่านั้นที่อยู่ใน repository เมื่อเพิ่มค่าลับใหม่ในบ่ายนี้ (เช่น token ใด ๆ ที่อาจต้องใช้) ต้องเพิ่มลง `.env` ของตนเอง **ไม่ใช่** ลงในโค้ดหรือใน `.env.example`

---

## 4. ชั้น 4 — ตัดข้อมูลลับก่อนส่งให้โมเดล

`apps/mcp-server/security/guardrails.py` มีฟังก์ชันสองตัวที่ทำหน้าที่นี้:

```python
def redact(text: str) -> str:
    """Strip anything that looks like a credential from outgoing text."""
```
*(`guardrails.py:141-153`)*

```python
def redact_deep(value):
    """Recursively redact strings inside dicts and lists."""
```
*(`guardrails.py:156-173`)*

**`redact_deep` ทำอะไร**: `redact()` ด้านบนทำงานกับ string เดี่ยวๆ เท่านั้น แต่ผลลัพธ์จริงที่ tool คืนกลับมักเป็น dict/list ซ้อนกันหลายชั้น (เช่น ผลลัพธ์จาก `search_tickets`) `redact_deep` จึงไล่เข้าไปทีละชั้นแบบ recursive ตามชนิดของค่าที่เจอ:

- เจอ **string** → ส่งเข้า `redact()` ตรงๆ (หา pattern เช่น `password: ...` ในเนื้อ string นั้น)
- เจอ **dict** → เช็ค**ชื่อ key** ก่อนเป็นอันดับแรก ถ้าชื่อ key เข้าข่ายเป็นความลับ (เช่น `password`, `api_key`) จะซ่อนทั้งค่านั้นทันทีไม่ว่าค่าข้างในจะหน้าตาเป็นอย่างไร ส่วน key อื่นๆ ที่เหลือจะเรียก `redact_deep` ซ้ำเข้าไปในค่านั้นต่อ
- เจอ **list** → เรียก `redact_deep` ซ้ำกับทุก element ข้างในทีละตัว
- เจอชนิดอื่น (int, bool, None) → ปล่อยผ่านเฉยๆ ไม่แตะ

ผลคือไม่ว่าความลับจะฝังอยู่ตื้นหรือลึกแค่ไหนในโครงสร้าง (string ธรรมดา, ค่าใน dict, หรือซ้อนอยู่ใน list ข้างใน dict อีกที) ก็จะถูกไล่ตรวจจนเจอ — ดูตัวอย่างรันได้ทันทีท้ายหัวข้อนี้ (หลังหัวข้อย่อย "เหตุใดต้องมีกรณีสำหรับ dict แยกต่างหาก" ด้านล่าง) ที่ทดสอบทั้งสองกรณีพร้อมกันในคำสั่งเดียว

ทดสอบได้จริงด้วยคำสั่งนี้ (รันแล้วขณะเตรียมเอกสารนี้ ได้ผลลัพธ์ตรงตามที่แสดง):

```bash
uv run python -c "import sys; sys.path.insert(0, 'apps/mcp-server'); from security.guardrails import redact; print(redact('snmp-server community public_snmp_read RO'))"
```

```
snmp-server community: [REDACTED] RO
```

### บั๊กจริงที่อธิบายว่าทำไม regex ต้องเขียนแบบนี้

`guardrails.py:123-126` มีคอมเมนต์อธิบาย pattern `_SECRET_NAME`:

```python
_SECRET_NAME = r"[\w-]*(?:password|passwd|secret|api[_-]?key|token|credential)s?"
```

ตัว `[\w-]*` นำหน้าคือส่วนสำคัญ: ถ้าเขียน regex แบบไร้เดียงสาว่า `\bpassword\b` มันจะ**ไม่** match คำว่า `PG_PASSWORD` เลย เพราะขีดล่าง (`_`) ถือเป็น word character การขึ้นต้นด้วย `\b` (word boundary) จึงไม่เกิดขึ้นตรงกลางคำแบบนั้น ผลคือรหัสผ่านที่ตั้งชื่อตามแบบที่ใช้จริงในโปรเจกต์นี้ (`PG_PASSWORD`, `NEO4J_PASSWORD`) จะรั่วไหลออกไปได้โดยไม่มีใครรู้ตัว — นี่คือบั๊กที่พบจริงตอนเขียนเทสของโปรเจกต์นี้ (บันทึกไว้ที่ `solutions/day3/README.md:50`)

**ตัวอย่างรันได้ทันที** — เทียบ regex ไร้เดียงสากับ regex ที่ใช้จริง กับข้อความเดียวกัน:

```bash
uv run python -c "
import re
naive = re.compile(r'\bpassword\b', re.IGNORECASE)
real = re.compile(r'(?i)\b([\w-]*(?:password|passwd|secret|api[_-]?key|token|credential)s?)\s*[:=]\s*\S+')
text = 'PG_PASSWORD=hunter2 NEO4J_PASSWORD=neo4j_dev_password'
print('naive regex เจอ:', naive.findall(text))
print('regex ที่ใช้จริง เจอ:', real.findall(text))
"
```

**ผลลัพธ์จริง** (รันจริงตอนเตรียมเอกสารนี้):

```
naive regex เจอ: []
regex ที่ใช้จริง เจอ: ['PG_PASSWORD', 'NEO4J_PASSWORD']
```

`naive` หาไม่เจอเลยสักคำ — ถ้าใช้ pattern นี้จริง ทั้ง `PG_PASSWORD` และ `NEO4J_PASSWORD` จะหลุดออกไปแบบไม่มีการเตือนใดๆ ทั้งที่ชื่อมันก็บอกอยู่ตรงๆ ว่าเป็นรหัสผ่าน

### เหตุใดต้องมีกรณีสำหรับ dict แยกต่างหาก

```python
_SECRET_KEY_RE = re.compile(rf"(?i)^{_SECRET_NAME}$")
```
*(`guardrails.py:138`)*

ในโครงสร้างแบบ `{"password": "hunter2"}` ไม่มี string เดี่ยว ๆ ที่มีทั้งชื่อฟิลด์และค่าอยู่ในตัวเดียวกันให้ pattern ด้านบนจับได้ `redact_deep` จึงตรวจสอบ **ชื่อ key เอง** ก่อนตัดสินใจว่าค่าของมันควรถูกซ่อนทั้งหมดหรือไม่ (`guardrails.py:163-170`)

**ตัวอย่างรันได้ทันที** — ทดสอบ `redact_deep` กับ dict ที่มีทั้ง key ชื่อ `password` และ string ที่ซ่อนอยู่ใน list ข้างในอีกที:

```bash
uv run python -c "
import sys
sys.path.insert(0, 'apps/mcp-server')
from security.guardrails import redact_deep
data = {'device_id': 'CR-BKK-01', 'password': 'hunter2', 'notes': ['snmp-server community public_snmp_read RO']}
print(redact_deep(data))
"
```

**ผลลัพธ์จริง** (รันจริงตอนเตรียมเอกสารนี้):

```
{'device_id': 'CR-BKK-01', 'password': '[REDACTED]', 'notes': ['snmp-server community: [REDACTED] RO']}
```

`device_id` ผ่านมาเฉยๆ เพราะไม่ใช่ชื่อ key หรือค่าที่หน้าตาเหมือนความลับ ส่วน `password` ถูกซ่อนทั้งค่าเพราะชื่อ key เข้าเงื่อนไข `_SECRET_KEY_RE` และ string ที่ซ้อนอยู่ใน list ก็ยังถูกไล่ตรวจต่อได้ (เพราะ `redact_deep` เรียกตัวเองซ้ำเข้าไปใน list ด้วย) — ยืนยันว่าการซ่อนข้อมูลทำงานได้ไม่ว่าความลับจะอยู่ตื้นหรือลึกแค่ไหนในโครงสร้าง

### ที่ที่ฟังก์ชันนี้ถูกเรียกใช้จริง

ทุก tool ที่คืนข้อมูลจากฐานข้อมูลใน `apps/mcp-server/tools/tickets.py` ห่อผลลัพธ์ด้วย `guardrails.redact_deep(...)` ก่อน return เสมอ เช่นใน `search_tickets`:

```python
return guardrails.redact_deep({
    "total_matches": total,
    ...
    "tickets": rows,
})
```
*(`apps/mcp-server/tools/tickets.py:92-98`)*

เหตุผลที่ต้องทำแม้บัญชีฐานข้อมูลเป็น read-only อยู่แล้ว: ข้อมูล config ของอุปกรณ์จริง (เช่น `config_markdown` ใน `get_device_config`) อาจมี SNMP community string หรือค่าที่หน้าตาเหมือนรหัสผ่านฝังอยู่ในเนื้อหาที่ engineer พิมพ์ไว้เอง — ชั้น 1 (read-only role) ป้องกันไม่ให้ "เขียน" ได้ แต่ไม่ได้ป้องกันไม่ให้ "อ่านแล้วส่งต่อ" ค่าลับที่ฝังอยู่ในข้อมูลปกติ ชั้น 4 จึงต้องมีแยกต่างหาก

---

## 5. สรุป: ทำไมต้องมีหลายชั้น พร้อมกัน

Read-only role (ชั้น 1) ปกป้องตัวข้อมูล ส่วน `assert_read_only` ในโค้ด (ชั้น 2, ดู `guardrails.py:79-90`) ปกป้องกรณีที่การตั้งค่าสิทธิ์ผิดพลาดในอนาคต และสร้าง audit log ที่อ่านเข้าใจง่ายทันที ทั้งสามอย่างนี้ (รวมถึงชั้น 3 และ 4) ไม่ได้ทำงานแทนกันได้ — แต่ละชั้นปิดช่องโหว่คนละแบบ การถอดชั้นใดชั้นหนึ่งออกจึงไม่ทำให้ระบบพังทั้งหมด นี่คือสิ่งที่โจทย์ที่ทดสอบความปลอดภัยของหลักสูตรนี้ (Red-team guardrail) ใช้วัดผล และเป็นมาตรฐานขั้นต่ำที่ MCP Server ที่จะสร้างใน Workshop 3 และ Workshop 4 บ่ายนี้ควรทำตาม อย่างน้อยในส่วนของ user แบบอ่านอย่างเดียวและการตัด secret

---

## ต่อไป

→ [Workshop 3: Customer Directory MCP Server](03-workshop3-customer-directory.md) — กิจกรรมสั้นๆ ก่อน จากนั้นตามด้วย [Workshop 4: MPLS NOC MCP Server](04-workshop4-mpls-noc-mcp-server.md)
