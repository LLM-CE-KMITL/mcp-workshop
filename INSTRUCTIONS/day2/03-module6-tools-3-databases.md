# Module 6 · เครื่องมือจาก 3 ฐานข้อมูล

**13:00 – 14:30** (90 นาที) · เป้าหมาย: ห่อ query จริงของ PostgreSQL, Neo4j และ OpenSearch ให้เป็น Tool ที่ ReAct loop เรียกได้ และเขียน Tool Description ที่ทำให้โมเดลเลือกเครื่องมือถูกตัว — ผลลัพธ์ของโมดูลนี้คือชุดเครื่องมือที่ Workshop 2 (ช่วงบ่าย) จะนำไปประกอบเป็น Agent ตัวเต็ม

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

## 4. แบบฝึกหัด: เขียน Tool Description สำหรับเครื่องมือตัวที่ 6

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

→ [Workshop 2: ReAct Agent สำหรับ NOC](04-workshop2-noc-agent.md) — ประกอบเครื่องมือทั้ง 6 ตัว (5 ตัวจากไฟล์เฉลย + `search_docs_semantic` ที่เพิ่งออกแบบ) เข้ากับ ReAct loop จาก Module 5 แล้วทดสอบกับโจทย์จริง 3 สถานการณ์
