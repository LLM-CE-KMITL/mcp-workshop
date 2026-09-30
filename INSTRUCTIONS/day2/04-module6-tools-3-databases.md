# Module 6 · เครื่องมือจาก 3 ฐานข้อมูล

**13:00 – 14:15** (75 นาที) · เป้าหมาย: ห่อ query จริงของ PostgreSQL, Neo4j และ OpenSearch ให้เป็น Tool ที่ ReAct loop เรียกได้ และเขียน Tool Description ที่ทำให้โมเดลเลือกเครื่องมือถูกตัว — ผลลัพธ์ของโมดูลนี้คือชุดเครื่องมือที่ Workshop 2 (ช่วงบ่าย) จะนำไปประกอบเป็น Agent ตัวเต็ม

---

## 1. Tool คือฟังก์ชัน Python ธรรมดา

จุดที่ทำให้ `solutions/day2/workshop2_agent.py` ไม่ต้องพึ่ง agent framework ใดๆ คือ **tool ไม่ใช่ class พิเศษหรือ decorator ที่ต้องเรียนรู้เพิ่ม** — เป็นฟังก์ชัน Python ธรรมดาที่มีสามอย่างครบ:

1. type hint ของ argument และ return value ที่ชัดเจน
2. docstring ที่บอกว่า "ใช้เมื่อไหร่"
3. ถูกลงทะเบียนไว้ใน dict ตัวเดียว

```python
# solutions/day2/workshop2_agent.py:210-216
TOOLS = {
    "search_tickets": search_tickets,
    "get_upstream_devices": get_upstream_devices,
    "count_log_events": count_log_events,
    "export_report": export_report,
    "send_notification": send_notification,
}
```

`TOOLS` ทำหน้าที่สองอย่างพร้อมกัน: เป็นแหล่งสร้างแคตตาล็อกที่ส่งให้โมเดล (ผ่าน `inspect.signature` — ดู Module 5 หัวข้อ 1.1) และเป็นจุดเดียวที่ตรวจสอบว่าชื่อ tool ที่โมเดลเลือกมีอยู่จริงหรือไม่ (`decision.tool not in TOOLS` — `solutions/day2/workshop2_agent.py:304`)

---

## 2. สามฐานข้อมูล สามรูปแบบ query

### 2.1 PostgreSQL — ข้อมูลเชิงสัมพันธ์ (`search_tickets`)

ใช้เมื่อคำถามต้องการรู้ว่ามีอะไรถูก **"แจ้ง"** เข้ามาบ้าง — เป็นข้อมูลเชิงสัมพันธ์ที่กรองด้วยเงื่อนไข `WHERE` หลายเงื่อนไขประกอบกัน:

```python
# solutions/day2/workshop2_agent.py:64-93
def search_tickets(status: str | None = None, days: int = 7,
                   limit: int = 20) -> dict:
    """ค้นหา ticket ที่ถูกแจ้งเข้ามา

    ใช้เมื่อต้องการรู้ว่ามีอะไรถูก "แจ้ง" เข้ามาบ้าง
    อย่าใช้เพื่อดูพฤติกรรมของอุปกรณ์ - ให้ใช้ count_log_events แทน
    """
    since = datetime.now(BANGKOK) - timedelta(days=days)
    where = ["opened_at >= %s"]
    params: list = [since]
    if status:
        where.append("status = %s")
        params.append(status)

    with psycopg.connect(PG_DSN) as conn:
        cur = conn.cursor()
        cur.execute(
            f"""SELECT ticket_id, severity, status, site_code, device_id,
                       title, opened_at
                FROM tickets WHERE {' AND '.join(where)}
                ORDER BY opened_at DESC LIMIT %s""",
            tuple(params + [limit]),
        )
        ...
```

สังเกตว่า connection ใช้ `PG_DSN` ที่ชี้ไปยัง `mcp_reader` — บัญชี **read-only** เท่านั้น (ดู `.env.example` หัวข้อ PostgreSQL) เป็นกติกาด้านความปลอดภัยที่ยึดตลอดทั้งหลักสูตร: tool ที่ Agent เรียกได้ต้องไม่มีสิทธิ์เขียนฐานข้อมูลจริงเด็ดขาด

**ตัวอย่างรันได้ทันที** — เรียกฟังก์ชันนี้ตรงๆ (ไม่ผ่าน LLM/loop) เพื่อดู query ที่แปลว่าอะไรจริงบน PostgreSQL:

```bash
uv run python -c "
import sys, json
sys.path.insert(0, 'solutions/day2')
from workshop2_agent import search_tickets
print(json.dumps(search_tickets(status='open', days=7), ensure_ascii=False, indent=2))
"
```

**ผลลัพธ์จริง** (รันจริงตอนเตรียมเอกสารนี้ — ตัวเลข ticket และเวลาที่เปิดจะต่างไปตามข้อมูลจริงในฐานข้อมูล ณ ขณะรัน):

```json
{
  "count": 3,
  "tickets": [
    {
      "ticket_id": "TK-25-00005",
      "severity": "high",
      "status": "open",
      "site_code": "NBI",
      "device_id": "LPE-NBI-12",
      "title": "เน็ตหลุดซ้ำ เคสเดิมที่เคยแจ้งไว้",
      "opened_at": "2026-09-24T09:26:22+07:00"
    },
    {
      "ticket_id": "TK-25-00018",
      "severity": "high",
      "status": "open",
      "site_code": "BKK",
      "device_id": "APE-BKK-05",
      "title": "วงจรล่ม ใช้งานไม่ได้ทั้งสาขา",
      "opened_at": "2026-09-24T02:28:16.896646+07:00"
    },
    {
      "ticket_id": "TK-25-00011",
      "severity": "high",
      "status": "open",
      "site_code": "NBI",
      "device_id": "LPE-NBI-12",
      "title": "โหลดไฟล์ช้ากว่าปกติมาก",
      "opened_at": "2026-09-23T16:27:47.957114+07:00"
    }
  ]
}
```

### 2.2 Neo4j — ความสัมพันธ์เชิงกราฟ (`get_upstream_devices`)

คำถามบางประเภทตอบด้วยตารางเดียวไม่ได้ เช่น "อุปกรณ์หลายตัวมี upstream ร่วมกันหรือไม่" — นี่คือจุดแข็งของฐานข้อมูลกราฟ:

```python
# solutions/day2/workshop2_agent.py:96-125
def get_upstream_devices(device_ids: list[str]) -> dict:
    """หาอุปกรณ์ upstream ที่อุปกรณ์หลายตัวใช้ร่วมกัน

    ใช้เมื่อลูกค้าหลายรายที่อยู่คนละอุปกรณ์แจ้งอาการเดียวกัน
    เพราะสาเหตุร่วมมักอยู่ที่อุปกรณ์ที่ทุกตัวพึ่งพา ซึ่ง ticket จะไม่เอ่ยถึง
    """
    ...
    with driver, driver.session() as session:
        records = session.run(
            """UNWIND $ids AS start
               MATCH (d:Device {device_id: start})-[:UPLINK_TO*1..4]->(up:Device)
               RETURN start, up.device_id AS upstream""",
            ids=device_ids,
        ).data()
```

Cypher pattern `-[:UPLINK_TO*1..4]->` เดินตามความสัมพันธ์ `UPLINK_TO` ได้ 1 ถึง 4 ชั้น — คือกลไกที่ทำให้ค้นพบว่า `LPE-NBI-11/12/13` แม้เป็นอุปกรณ์คนละตัว แต่ทั้งหมด uplink ไปยัง `APE-NBI-03` ตัวเดียวกัน (ดูตัวอย่างเหตุการณ์เต็มใน `data/scenarios.md` หัวข้อ S1) จุดสำคัญของ docstring นี้คือบอก**เมื่อไหร่ควรเรียก** ไม่ใช่แค่ว่าเครื่องมือทำอะไร — "ลูกค้าหลายรายที่อยู่คนละอุปกรณ์แจ้งอาการเดียวกัน" เป็นสัญญาณที่โมเดลต้องจับได้จากคำถามผู้ใช้เอง

**ตัวอย่างรันได้ทันที** — เรียกฟังก์ชันนี้ตรงๆ ด้วยอุปกรณ์ 3 ตัวจากเหตุการณ์ S1 (`data/scenarios.md`) เพื่อดูว่ากราฟหา upstream ร่วมได้จริงอย่างไร:

```bash
uv run python -c "
import sys, json
sys.path.insert(0, 'solutions/day2')
from workshop2_agent import get_upstream_devices
print(json.dumps(get_upstream_devices(['LPE-NBI-11', 'LPE-NBI-12', 'LPE-NBI-13']), ensure_ascii=False, indent=2))
"
```

**ผลลัพธ์จริง** (รันจริงตอนเตรียมเอกสารนี้):

```json
{
  "upstream_devices": [
    {
      "device_id": "APE-NBI-03",
      "dependent_count": 3,
      "depends_on_it": ["LPE-NBI-11", "LPE-NBI-12", "LPE-NBI-13"]
    },
    {
      "device_id": "PE-NBI-01",
      "dependent_count": 3,
      "depends_on_it": ["LPE-NBI-11", "LPE-NBI-12", "LPE-NBI-13"]
    },
    {
      "device_id": "CR-BKK-01",
      "dependent_count": 3,
      "depends_on_it": ["LPE-NBI-11", "LPE-NBI-12", "LPE-NBI-13"]
    }
  ],
  "shared_by_all": [
    {
      "device_id": "APE-NBI-03",
      "dependent_count": 3,
      "depends_on_it": ["LPE-NBI-11", "LPE-NBI-12", "LPE-NBI-13"]
    },
    {
      "device_id": "PE-NBI-01",
      "dependent_count": 3,
      "depends_on_it": ["LPE-NBI-11", "LPE-NBI-12", "LPE-NBI-13"]
    },
    {
      "device_id": "CR-BKK-01",
      "dependent_count": 3,
      "depends_on_it": ["LPE-NBI-11", "LPE-NBI-12", "LPE-NBI-13"]
    }
  ]
}
```

`shared_by_all` เหมือน `upstream_devices` เป๊ะในตัวอย่างนี้เพราะทั้งสามอุปกรณ์ที่ส่งเข้าไป uplink ไปหาต้นทางเดียวกันครบทุกตัว (`dependent_count == len(device_ids)` ทุกแถว) — ถ้าส่งอุปกรณ์ที่ไม่ได้ uplink ร่วมกันทั้งหมดเข้าไป สองรายการนี้จะเริ่มต่างกัน (`upstream_devices` จะมีแถวที่ `dependent_count` ต่ำกว่าจำนวนอุปกรณ์ที่ส่งเข้าไป แต่ `shared_by_all` จะกรองแถวเหล่านั้นออก)

### 2.3 OpenSearch — นับและรวมยอด log จำนวนมาก (`count_log_events`)

ใช้เมื่อคำถามคือ "กี่ครั้ง" หรือ "ตัวไหนเยอะที่สุด" — เป็นงาน aggregation ที่ SQL ทำได้แต่ไม่มีประสิทธิภาพเท่าที่ log มีปริมาณสูง:

```python
# solutions/day2/workshop2_agent.py:128-150
def count_log_events(days: int = 7, group_by: str = "device_id") -> dict:
    """นับ log events แยกตามอุปกรณ์หรือประเภทเหตุการณ์

    ใช้เมื่อถามว่า "กี่ครั้ง" หรือ "ตัวไหนเยอะที่สุด"
    อย่าใช้เมื่อต้องการอ่านข้อความ log จริง
    """
    client = OpenSearch(hosts=[os.getenv("OPENSEARCH_URL", "http://localhost:9200")])
    response = client.search(
        index="network-logs-*",
        body={
            "size": 0,
            "query": {"bool": {"must": [
                {"range": {"@timestamp": {"gte": f"now-{days}d"}}},
                {"terms": {"severity": ["critical", "error", "warning"]}},
            ]}},
            "aggs": {"grouped": {"terms": {"field": group_by, "size": 15}}},
        },
    )
```

`"size": 0` คือรายละเอียดที่มักถูกมองข้าม — บอก OpenSearch ว่าไม่ต้องการเอกสารดิบกลับมาเลย ต้องการเฉพาะผลรวมจาก `aggs` เท่านั้น ประหยัดทั้ง bandwidth และ token ที่ต้องส่งกลับให้ LLM อ่านเป็น observation

**ตัวอย่างรันได้ทันที** — เรียกฟังก์ชันนี้ตรงๆ เพื่อดูผล aggregation จริงจาก OpenSearch:

```bash
uv run python -c "
import sys, json
sys.path.insert(0, 'solutions/day2')
from workshop2_agent import count_log_events
print(json.dumps(count_log_events(days=7, group_by='device_id'), ensure_ascii=False, indent=2))
"
```

**ผลลัพธ์จริง** (รันจริงตอนเตรียมเอกสารนี้ — ถ้าได้ `\"total\": 0` แปลว่า timestamp ของ log หลุดหน้าต่าง `now-7d` ไปแล้ว ดูวิธี refresh ใน [Module 4 หัวข้อ 4](01-module4-react-pattern.md)):

```json
{
  "total": 146,
  "results": [
    {"key": "APE-BKK-05", "count": 75},
    {"key": "APE-NBI-03", "count": 18},
    {"key": "PE-BKK-02", "count": 18},
    {"key": "PE-NBI-04", "count": 9},
    {"key": "PE-NBI-01", "count": 7},
    {"key": "LPE-NBI-11", "count": 5},
    {"key": "LPE-NBI-12", "count": 4},
    {"key": "LPE-NBI-13", "count": 4},
    {"key": "CR-BKK-01", "count": 3},
    {"key": "CR-BKK-02", "count": 3}
  ]
}
```

สังเกตว่า `total` (146) มากกว่าผลรวมของทุก `count` ใน `results` (75+18+18+9+7+5+4+4+3+3 = 146 พอดีในตัวอย่างนี้เพราะ `size: 15` ครอบคลุมทุก `device_id` ที่มีจริง) — ถ้าอุปกรณ์มีมากกว่า 15 ตัว `results` จะโดนตัดอันดับท้ายออกตาม `"size": 15` ใน `terms` aggregation แต่ `total` ยังนับครบทุก log ที่ผ่านเงื่อนไข `range`/`terms` ด้านบนเสมอ

---

## 3. เขียน Tool Description ที่ดี

โมเดลไม่เห็นซอร์สโค้ดของฟังก์ชันเลย เห็นแค่สิ่งที่ catalogue ส่งไป (ชื่อ + signature + docstring) การเลือกเครื่องมือผิดตัวจึงมักไม่ใช่ความผิดของโมเดล แต่เป็นเพราะ description เขียนไม่ชัด

สังเกตรูปแบบร่วมของทั้งสาม docstring ข้างต้น — **มีสองประโยคเสมอ ไม่ใช่ประโยคเดียว**:

1. ประโยคแรก: ใช้เมื่อไหร่ ("ใช้เมื่อต้องการรู้ว่ามีอะไรถูก 'แจ้ง' เข้ามาบ้าง")
2. ประโยคที่สอง: **อย่าใช้เมื่อไหร่** พร้อมชี้ไปยังเครื่องมือที่ถูกต้องแทน ("อย่าใช้เพื่อดูพฤติกรรมของอุปกรณ์ - ให้ใช้ `count_log_events` แทน")

ประโยคที่สองสำคัญไม่น้อยกว่าประโยคแรก เพราะ `search_tickets` (สิ่งที่ลูกค้า "แจ้ง") กับ `count_log_events` (สิ่งที่อุปกรณ์ "ทำจริง") เป็นสองมุมมองของเหตุการณ์เดียวกันที่ทับซ้อนกันได้ง่ายในสายตาโมเดล — เหตุการณ์ S4 ใน `data/scenarios.md` (log critical จำนวนมากที่กลับกลายเป็นงานบำรุงรักษาตามแผน) คือตัวอย่างที่ถ้า Agent ดู log อย่างเดียวโดยไม่ตรวจ ticket ประเภท `maintenance` ก่อน จะสรุปผิดทันที

**หลักการเขียน Tool Description สั้นๆ**

- บอกเมื่อไหร่ควรเรียก **และ** เมื่อไหร่ไม่ควรเรียก (negative example ชี้ไปยังเครื่องมือที่ถูกต้อง)
- อย่าเขียนรายละเอียด argument ซ้ำใน docstring — `inspect.signature(fn)` ให้ signature ไปพร้อมกันอยู่แล้วใน catalogue (ดู Module 5 หัวข้อ 1.1) การเขียนซ้ำมีแต่จะไม่ตรงกันเมื่อแก้โค้ดภายหลัง
- สั้นที่สุดเท่าที่ยังทำให้แยกจากเครื่องมือตัวอื่นได้ชัดเจน — ยิ่งยาวยิ่งกินความสนใจของโมเดลในทุกรอบของ loop (docstring ถูกส่งซ้ำทุก step ไม่ใช่ส่งครั้งเดียว)

---

## 4. พิสูจน์ว่า Tool Description ทำงานจริง: ให้ LLM เลือกเองผ่าน loop

ตัวอย่างในหัวข้อ 2 ข้างบนทั้งหมดเรียกฟังก์ชัน tool ตรงๆ ด้วยมือ (ไม่ผ่านโมเดล) — ตัวอย่างนี้เอาเครื่องมือทั้ง 3 ตัวจริง (`search_tickets`, `get_upstream_devices`, `count_log_events`) ไปให้ **LLM จริงเลือกเอง** ทีละคำถาม เพื่อพิสูจน์ว่า Tool Description ที่ออกแบบตามหลักการในหัวข้อ 3 ทำให้โมเดลเลือกเครื่องมือถูกตัวจริง (ไม่ใช่แค่ในทฤษฎี):

```bash
uv run python -c "
import asyncio, sys, inspect, json
from dotenv import load_dotenv; load_dotenv()
sys.path.insert(0, 'apps/agent-api')
sys.path.insert(0, 'solutions/day2')
from agent import llm
from workshop2_agent import search_tickets, get_upstream_devices, count_log_events
from pydantic import BaseModel

class ReactDecision(BaseModel):
    thought: str
    tool: str | None = None
    arguments: dict = {}

TOOLS = {
    'search_tickets': search_tickets,
    'get_upstream_devices': get_upstream_devices,
    'count_log_events': count_log_events,
}
catalogue = '\n\n'.join(
    f'{name}{inspect.signature(fn)}: {(fn.__doc__ or \"\").strip()}' for name, fn in TOOLS.items()
)

PROMPT = f'''คุณคือ agent ที่ตัดสินใจทีละขั้นตอนเดียว (ห้ามวางแผนล่วงหน้าหลายขั้นตอน)

เครื่องมือที่มี:
{catalogue}

ตอบเป็น JSON ตามรูปแบบ:
{{\"thought\": \"เหตุผลสั้นๆ\", \"tool\": \"ชื่อเครื่องมือ หรือ null\", \"arguments\": {{}}}}
'''

async def decide(question):
    messages = [
        {'role': 'system', 'content': PROMPT},
        {'role': 'user', 'content': question},
    ]
    return await llm.complete_structured(messages, ReactDecision)

async def main():
    questions = [
        'มี ticket severity สูงที่ยังไม่ปิดอยู่กี่ใบในสัปดาห์นี้',
        'อุปกรณ์ LPE-NBI-11, LPE-NBI-12 และ LPE-NBI-13 มี upstream ร่วมกันไหม',
        'เจอ log error หรือ critical กี่ครั้งในช่วง 7 วันที่ผ่านมา แยกตามอุปกรณ์',
    ]
    for q in questions:
        d = await decide(q)
        print(f'คำถาม: {q}')
        print(f'  Thought: {d.thought}')
        print(f'  Action: {d.tool}({d.arguments})')
        result = TOOLS[d.tool](**d.arguments)
        print(f'  Observation: {json.dumps(result, ensure_ascii=False)[:150]}...')
        print('-'*60)

asyncio.run(main())
"
```

**ผลลัพธ์จริง** (รันจริงตอนเตรียมเอกสารนี้ — ใช้ `llm.complete_structured()` จาก `apps/agent-api/agent/llm.py` ซึ่ง forced JSON ด้วย schema เดียวกับที่ `decide_next_step()` ใช้จริงใน `solutions/day2/workshop2_agent.py`):

```
คำถาม: มี ticket severity สูงที่ยังไม่ปิดอยู่กี่ใบในสัปดาห์นี้
  Thought: ต้องการนับจำนวน ticket ที่ยังไม่ปิดและมี severity สูงในช่วง 7 วันที่ผ่านมา
  Action: search_tickets({'status': 'open', 'days': 7, 'limit': 20})
  Observation: {"count": 3, "tickets": [{"ticket_id": "TK-25-00005", "severity": "high", "status": "open", "site_code": "NBI", "device_id": "LPE-NBI-12", "title": "เ...
------------------------------------------------------------
คำถาม: อุปกรณ์ LPE-NBI-11, LPE-NBI-12 และ LPE-NBI-13 มี upstream ร่วมกันไหม
  Thought: ต้องการตรวจสอบว่าอุปกรณ์ทั้งสามมี upstream ร่วมกันหรือไม่
  Action: get_upstream_devices({'device_ids': ['LPE-NBI-11', 'LPE-NBI-12', 'LPE-NBI-13']})
  Observation: {"upstream_devices": [{"device_id": "APE-NBI-03", "dependent_count": 3, "depends_on_it": ["LPE-NBI-11", "LPE-NBI-12", "LPE-NBI-13"]}, {"device_id": "P...
------------------------------------------------------------
คำถาม: เจอ log error หรือ critical กี่ครั้งในช่วง 7 วันที่ผ่านมา แยกตามอุปกรณ์
  Thought: ต้องการนับจำนวน log events ที่เป็น error หรือ critical ในช่วง 7 วัน แยกตามอุปกรณ์
  Action: count_log_events({'days': 7, 'group_by': 'device_id'})
  Observation: {"total": 143, "results": [{"key": "APE-BKK-05", "count": 75}, {"key": "APE-NBI-03", "count": 18}, {"key": "PE-BKK-02", "count": 18}, {"key": "PE-NBI-...
------------------------------------------------------------
```

**สังเกต**: ทั้งสามคำถามถูกออกแบบให้ "ใกล้เคียงกัน" โดยตั้งใจ — คำถามแรกถามเรื่อง ticket (สิ่งที่ถูก "แจ้ง"), คำถามที่สามถามเรื่อง log (สิ่งที่อุปกรณ์ "ทำจริง") ซึ่งเป็นคู่ที่หัวข้อ 3 เตือนไว้ว่าทับซ้อนกันได้ง่าย แต่โมเดลก็ยังแยกถูกทั้งคู่ เพราะประโยคที่สองของแต่ละ docstring ("อย่าใช้เมื่อ...") ตัดความกำกวมไปตั้งแต่ในแคตตาล็อกแล้ว — นี่คือหนึ่งก้าว (Thought → Action → Observation) ของ ReAct loop ต่อคำถาม ไม่ใช่ loop เต็มรูปแบบที่วนหลายรอบ (ดู loop เต็มที่ [Module 5](03-module5-react-loop.md))

---

## 5. แบบฝึกหัด: เขียน Tool Description สำหรับเครื่องมือตัวที่ 6

Workshop 2 (ช่วงบ่ายถัดไป) ใช้เครื่องมือ **6 ตัว** ไม่ใช่ 5 — ห้าตัวแรกคือของที่ผ่านมา บวกด้วยเครื่องมือใหม่ที่ต้องออกแบบเอง: **`search_docs_semantic`** ทำ semantic search เหนือ runbook/เอกสาร config แทนที่จะเป็น ticket

ข้อมูลตั้งต้นสำหรับออกแบบ:

- ดัชนี OpenSearch `network-docs*` ถูก ingest ไว้แล้วโดย Lab เสริมของวันที่ 1 (`scripts/ingest_docs.py`) จาก runbook ใน `data/mock_fs/runbooks/*.md` — ใช้โมเดล embedding เดียวกับที่ใช้กับ ticket ใน Lab 1 (`EMBEDDING_MODEL=baai/bge-m3`, `EMBEDDING_DIM=1024` ตาม `.env.example`)
- โครงสร้างฟิลด์จริงของดัชนีอยู่ใน `docker/opensearch/seed/doc_index_template.json` — มี `title`, `source_type`, `device_id`, `site_code`, `tags`, `content` และ `embedding` (ชนิด `knn_vector`, dimension 1024, `space_type: cosinesimil`)
- รูปแบบ query แบบ knn เดียวกับที่ใช้ใน `scripts/compare_vector_stores.py` (`try_opensearch`): `{"query": {"knn": {"embedding": {"vector": vector, "k": k}}}}`

**สิ่งที่ต้องทำ** — เขียนเฉพาะ **signature และ docstring** ของ `search_docs_semantic` (ยังไม่ต้องเขียน body เต็ม — การต่อ embedding endpoint จริงและประกอบเป็น tool ที่ใช้งานได้ทำใน Workshop 2):

```python
def search_docs_semantic(query: str, top_k: int = 5) -> dict:
    """<เขียนเอง — ให้ตามรูปแบบสองประโยคของหัวข้อ 3>
    """
```

ให้ตอบคำถามต่อไปนี้ในสองประโยคของ docstring: เมื่อไหร่ควรเรียกเครื่องมือนี้แทน `search_tickets`? และเมื่อไหร่ไม่ควรเรียก (เช่น ถ้าต้องการนับจำนวนหรือดูตัวเลข ควรใช้ `count_log_events` แทน)?

### เกณฑ์ผ่าน

- [ ] docstring มีทั้งประโยค "ใช้เมื่อ" และ "อย่าใช้เมื่อ" ตามรูปแบบของหัวข้อ 3
- [ ] เปรียบเทียบกับเพื่อนร่วมกลุ่มอย่างน้อย 1 คน — docstring ที่ต่างคำแต่ความหมายตรงกันถือว่าผ่าน
- [ ] อธิบายได้ว่าทำไม `search_docs_semantic` กับ `search_tickets` ไม่ทับซ้อนกัน ทั้งที่ทั้งคู่ "ค้นหา" เหมือนกัน

### สิ่งที่ต้องส่ง

ข้อความ docstring ที่เขียน (ไม่ต้องมีไฟล์แยก) — วางไว้ในช่องทางที่วิทยากรแจ้ง จะถูกใช้ต่อจริงเป็นจุดเริ่มต้นของ Workshop 2

---

## ต่อไป

→ [Module 8: Memory](05-module8-memory.md) — ก่อนประกอบเป็น Agent เต็มรูปแบบใน Workshop 2 ต้องรู้ก่อนว่าจะจำบทสนทนาข้าม turn อย่างไรโดยไม่ให้ context บวมจนเกินงบ
