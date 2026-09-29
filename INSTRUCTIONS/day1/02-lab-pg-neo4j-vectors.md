# Lab · Vector ใน PostgreSQL และ Neo4j

**10:30 – 11:30** (60 นาที) · ต่อจาก Module 1 · เป้าหมาย: สร้าง vector column และ vector index ให้ทำงานได้จริงด้วยมือตัวเองในสองฐานข้อมูล ก่อนที่ Module 2 จะไปทำแบบเดียวกันกับ OpenSearch

---

## เป้าหมาย

ดำเนินการสร้าง pipeline ของ semantic search ครบวงจรด้วยตนเอง ตั้งแต่เพิ่ม column/index → สร้าง embedding → backfill → ค้นหา — ใน **สองฐานข้อมูล** ที่เก็บ vector ต่างกันคนละแบบ (คอลัมน์ใน PostgreSQL เทียบกับ property ของ node ใน Neo4j)

ระบบตอนนี้ **มี embedding พร้อมใช้งานอยู่แล้ว** ทั้งสองฝั่ง ขั้นแรกของ lab คือลบมันทิ้ง เพื่อให้ได้สร้างขึ้นใหม่ด้วยตนเอง

---

## ขั้นที่ 0 · ดูของเดิมก่อนลบ

เปิด **pgAdmin** ([http://localhost:5050](http://localhost:5050), login `workshop@example.com` / `workshop`) รัน:

```sql
SELECT count(*) AS total, count(embedding) AS embedded FROM tickets;
```

เปิด **Neo4j Browser** ([http://localhost:7474](http://localhost:7474), login `neo4j` / `neo4j_dev_password`) รัน:

```cypher
MATCH (n) WHERE n.embedding IS NOT NULL RETURN labels(n)[0] AS label, count(n) AS n;
```

ลองถามคำถามที่ต้องใช้ semantic search ผ่าน Chainlit หรือ MCP Inspector ก่อน เช่น *"ทำไมช่วงนี้มีลูกค้าแจ้งเน็ตหลุดซ้ำๆ หลายราย"* — ควรทำงานได้ปกติ

---

## ขั้นที่ 1 · ลบทิ้ง

**pgAdmin** — รัน:

```sql
DROP INDEX IF EXISTS idx_tickets_embedding;
ALTER TABLE tickets DROP COLUMN IF EXISTS embedding;

-- ยืนยันผล ควรได้ 0 แถว
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'tickets' AND column_name = 'embedding';
```

**Neo4j Browser** — รัน:

```cypher
DROP INDEX device_embedding IF EXISTS;
DROP INDEX circuit_embedding IF EXISTS;

MATCH (d:Device)  REMOVE d.embedding;
MATCH (c:Circuit) REMOVE c.embedding;

// ยืนยันผล ควรได้ 0
MATCH (n) WHERE n.embedding IS NOT NULL RETURN count(n) AS nodes_with_embedding;
```

คำสั่งทั้งสองก้อนข้างบนคือสิ่งที่ [`make lab1-reset`](../../Makefile) รันให้อัตโนมัติทั้งสองฐานข้อมูลพร้อมกัน — ใช้คำสั่งเดียวนี้แทนการเปิด pgAdmin/Neo4j Browser สองหน้าต่างก็ได้ ยืนยันผลได้จากตัวเลขที่คำสั่งพิมพ์ออกมา ควรเห็น `0 rows` และ `nodes_with_embedding = 0`

```bash
make lab1-reset
```

ลองถามคำถามเดิมจากขั้นที่ 0 อีกครั้ง — ระบบควรตอบว่ายังไม่มี embedding หรือค้นไม่เจอ

---

## ขั้นที่ 2 · PostgreSQL — เพิ่ม column

**เหตุผลที่ต้องใช้ 1024** — ต้องตรงกับมิติของโมเดล embedding (`EMBEDDING_DIM` ใน `.env`) หากกำหนดผิด `UPDATE` จะ error ทุกแถวตั้งแต่แถวแรก

```sql
ALTER TABLE tickets ADD COLUMN embedding vector(1024);
```

ตรวจสอบว่า column ถูกสร้างจริง (ควรเห็น 1 แถว, `udt_name` เป็น `vector`):

```sql
SELECT column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_name = 'tickets' AND column_name = 'embedding';
```

ตอนนี้ column ยังว่างเปล่า (ยังไม่ backfill) — ยืนยันด้วยคำสั่งเดียวกับขั้นที่ 0:

```sql
SELECT count(*) AS total, count(embedding) AS embedded FROM tickets;
```

ควรได้ `embedded = 0` (ถ้าไม่ใช่ 0 แปลว่าขั้นที่ 1 ลบไม่หมด ย้อนกลับไปเช็คก่อน)

---

## ขั้นที่ 3 · PostgreSQL — สร้าง embedding และ backfill

เขียนสคริปต์ของตัวเอง บันทึกเป็น `pg_backfill_tickets.py` ที่ root ของโปรเจกต์ (โครงเดียวกับที่ [`scripts/embed_tickets.py`](../../scripts/embed_tickets.py) ใช้จริง — เรียก `EMBEDDING_BASE_URL/embeddings` แบบ OpenAI-compatible, เรียงผลตาม `index` ก่อนจับคู่กับแถวเสมอเพราะ API ไม่รับประกันลำดับ, ยิงเป็น batch ไม่ใช่ทีละแถว):

```python
import os
import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv(".env")

PG_DSN = os.getenv("PG_ADMIN_DSN", "postgresql://mpls:mpls_dev_password@localhost:5432/mplsdb")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "baai/bge-m3")

def embed_batch(texts: list[str]) -> list[list[float]]:
    r = httpx.post(
        f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
        json={"model": EMBEDDING_MODEL, "input": texts},
        headers={"Authorization": f"Bearer {os.getenv('LLM_API_KEY', 'not-needed')}"},
        timeout=90,
    )
    r.raise_for_status()
    ordered = sorted(r.json()["data"], key=lambda d: d["index"])  # ห้ามข้ามขั้นนี้
    return [d["embedding"] for d in ordered]

with psycopg.connect(PG_DSN) as conn:
    cur = conn.cursor()
    cur.execute("SELECT ticket_id, title, description FROM tickets ORDER BY ticket_id")
    rows = cur.fetchall()

    BATCH = 32
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        vectors = embed_batch([f"{t}\n\n{d}" for _, t, d in chunk])
        for (ticket_id, _, _), vec in zip(chunk, vectors):
            cur.execute("UPDATE tickets SET embedding = %s::vector WHERE ticket_id = %s",
                        (str(vec), ticket_id))
        conn.commit()
        print(f"{i + len(chunk)}/{len(rows)}")
```

รันด้วย:

```bash
uv run python pg_backfill_tickets.py
```

**ผลลัพธ์ที่ควรเห็น** (รันจริงตอนเตรียมเอกสารนี้):

```
Embedding 117 tickets with baai/bge-m3
    32/117
    64/117
    96/117
    117/117

  Done: 117/117 tickets have embeddings
```

### ข้อผิดพลาดที่พบบ่อย 3 ประการ

| ข้อผิดพลาด | ผลที่เกิดขึ้น |
|---|---|
| ไม่เรียง `data` ตาม `index` ก่อนจับคู่กับแถว | **ไม่มี error ใดๆ** แต่ vector ไปผูกกับ ticket ผิดใบ ค้นแล้วได้ผลลัพธ์ที่ไม่ถูกต้อง |
| ส่งคำขอ embed ทีละแถว แทนที่จะเป็น batch | 117 แถวใช้เวลาหลายนาที แทนที่จะเป็นไม่กี่วินาที |
| embed แค่ `title` ไม่รวม `description` | ค้นเจอผลลัพธ์น้อยลงมาก เพราะรายละเอียดอาการมักอยู่ใน `description` ไม่ใช่หัวเรื่อง |

ข้อแรกอันตรายที่สุด เพราะระบบยังทำงานได้ปกติทุกอย่าง มีเพียงคำตอบที่ผิดพลาดโดยไม่มีสัญญาณเตือนใดๆ

---

## ขั้นที่ 4 · PostgreSQL — สร้าง index

สร้าง index **หลัง**จาก backfill เสร็จเท่านั้น (HNSW ที่สร้างบนตารางว่างแล้วค่อยเติมทีละแถวจะได้กราฟที่คุณภาพแย่กว่าและค้นช้ากว่า):

```sql
CREATE INDEX idx_tickets_embedding ON tickets
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

ตรวจสอบว่า index ถูกสร้างจริง (ควรเห็น 1 แถว, `indexdef` มีคำว่า `hnsw`):

```sql
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename = 'tickets' AND indexname = 'idx_tickets_embedding';
```

---

## ขั้นที่ 5 · PostgreSQL — ทดสอบค้นหา

```mermaid
flowchart LR
    A["คำค้นภาษาไทย<br/>'ลูกค้าแจ้งเน็ตหลุดเป็นช่วง ๆ ที่ไซต์ NBI'"] --> B["Embedding endpoint<br/>baai/bge-m3"]
    B --> C["query vector<br/>1024 มิติ"]
    C --> D["PostgreSQL<br/>ORDER BY embedding &lt;=&gt; query_vec"]
    D --> E["ticket 5 อันดับแรก<br/>เรียงตาม distance (น้อย = ใกล้)"]
```

embed คำถามด้วยฟังก์ชันเดียวกับขั้นที่ 3 แล้วค้นด้วย `<=>` (cosine distance ใน pgvector ยิ่งน้อยยิ่งใกล้):

```sql
SELECT ticket_id, title, embedding <=> '[...]'::vector AS distance
FROM tickets
ORDER BY embedding <=> '[...]'::vector
LIMIT 5;
```

**ผลลัพธ์ที่ควรเห็น** สำหรับคำค้น `"ลูกค้าแจ้งเน็ตหลุดเป็นช่วง ๆ ที่ไซต์ NBI"`:

```
('TK-25-00001', 'อินเทอร์เน็ตหลุดเป็นช่วงๆ ตั้งแต่เมื่อวาน', 0.2947)
('TK-25-00005', 'เน็ตหลุดซ้ำ เคสเดิมที่เคยแจ้งไว้', 0.3624)
('TK-25-00002', 'เน็ตกระตุกเป็นช่วง ใช้งานไม่ต่อเนื่อง', 0.3717)
('TK-25-00004', 'หลุดบ่อยช่วงบ่าย', 0.4159)
('TK-25-00015', 'latency สูงผิดปกติช่วงเย็น', 0.5052)
```

ticket แถวบนสุดควรอยู่ในหมวดที่เกี่ยวข้องกับ "เน็ตหลุดเป็นช่วงๆ" โดยตรง หากได้ผลลัพธ์ที่ไม่เกี่ยวข้องเลย ให้ย้อนกลับไปตรวจว่า backfill ในขั้นที่ 3 เสร็จสมบูรณ์จริงหรือยัง (`embedded = total` หรือไม่)

---

## ขั้นที่ 6 · Neo4j — สร้าง vector index แล้ว backfill

Neo4j เก็บ vector เป็น **property ของ node โดยตรง** ไม่ใช่คอลัมน์แยกแบบ PostgreSQL และต้องสร้าง index สองตัวแยกกัน เพราะมีสอง label ที่ต้องการ semantic search (`Device` และ `Circuit`) — **สร้าง index ก่อน**ได้เลยแม้ node ยังไม่มี property `embedding` เลยก็ตาม (ต่างจาก HNSW ของ pgvector ในขั้นที่ 4 ที่ต้องรอ backfill ก่อน):

```cypher
CREATE VECTOR INDEX device_embedding IF NOT EXISTS
FOR (d:Device) ON (d.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};

CREATE VECTOR INDEX circuit_embedding IF NOT EXISTS
FOR (c:Circuit) ON (c.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};
```

ตรวจสอบว่า index ถูกสร้างจริง (ควรเห็น 2 แถว สถานะ `ONLINE`):

```cypher
SHOW VECTOR INDEXES YIELD name, state WHERE name IN ['device_embedding', 'circuit_embedding'];
```

ข้อความที่ต้อง embed ไม่ใช่ทั้ง node แต่เป็นฟิลด์ `profile_text` ที่ seed ไว้ให้แล้ว — ตัวอย่างจริง: `"CR-BKK-01 is a core router carrying backbone transit between sites. Located at site BKK. Management address 10.10.0.1. Interfaces: Hu0/0/0/0, Hu0/0/0/1, Hu0/0/0/2."`

เขียนสคริปต์ของตัวเอง บันทึกเป็น `neo4j_backfill_profiles.py` (โครงเดียวกับ [`scripts/embed_devices.py`](../../scripts/embed_devices.py) — วนทั้งสอง label ในลูปเดียว เพราะ logic เหมือนกันทุกประการ ต่างแค่ label):

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "neo4j_dev_password")),
)
with driver, driver.session() as session:
    for label, key in (("Device", "device_id"), ("Circuit", "circuit_id")):
        records = session.run(
            f"MATCH (n:{label}) WHERE n.profile_text IS NOT NULL "
            f"RETURN n.{key} AS id, n.profile_text AS text"
        ).data()
        vectors = embed_batch([r["text"] for r in records])
        for record, vector in zip(records, vectors):
            session.run(f"MATCH (n:{label} {{{key}: $id}}) SET n.embedding = $vec",
                        id=record["id"], vec=vector)
        print(f"embedded {len(records)} {label} nodes")
```

รันด้วย:

```bash
uv run python neo4j_backfill_profiles.py
```

**ผลลัพธ์ที่ควรเห็น**:

```
embedded 10 Device nodes
embedded 35 Circuit nodes

45 nodes now carry embeddings
```

ยืนยันด้วยคำสั่งเดียวกับขั้นที่ 0:

```cypher
MATCH (n) WHERE n.embedding IS NOT NULL RETURN labels(n)[0] AS label, count(n) AS n;
```

ควรได้ `Device = 10` และ `Circuit = 35`

---

## ขั้นที่ 7 · Neo4j — ทดสอบค้นหา

ทดสอบค้นหาจริงผ่าน `db.index.vector.queryNodes`:

```cypher
MATCH (d:Device {device_id: "CR-BKK-01"})
CALL db.index.vector.queryNodes('device_embedding', 3, d.embedding)
YIELD node, score
RETURN node.device_id AS id, score
```

**ผลลัพธ์ที่ควรเห็น** — ค้นหาอุปกรณ์ที่ใกล้เคียงกับ `CR-BKK-01` เอง:

```
{'id': 'CR-BKK-01', 'score': 0.9996}
{'id': 'CR-BKK-02', 'score': 0.9792}
{'id': 'PE-BKK-02', 'score': 0.8869}
```

**สังเกต**: อุปกรณ์ตัวเองได้คะแนนสูงสุดเสมอ (ใกล้ 1.0) ตามด้วย `CR-BKK-02` ซึ่งเป็น core router เหมือนกัน — นี่คือหลักฐานว่า embedding จับ "บทบาทของอุปกรณ์" ได้ ไม่ใช่แค่จับชื่อที่คล้ายกัน

---

## ทำไม Neo4j ต้องมีของตัวเอง ทั้งที่มี pgvector อยู่แล้ว

เหตุผลไม่ใช่ความซ้ำซ้อน แต่เป็นความสามารถที่ pgvector ให้ไม่ได้: **ผลจาก semantic search ใน Neo4j เดินกราฟต่อได้ทันทีในคำสั่งเดียว** — หาอุปกรณ์ที่คล้ายกันเชิงความหมายแล้วถามต่อได้เลยว่าอุปกรณ์นั้นมี upstream อะไรบ้าง โดยไม่ต้องเอาผลลัพธ์ไปสืบต่อในระบบอื่น ต่างจาก pgvector ที่ตอบได้แค่ "ใกล้เคียงกัน" อย่างเดียว

---

## เกณฑ์ผ่าน

- [ ] `ALTER TABLE tickets ADD COLUMN embedding vector(1024)` สำเร็จ และ backfill ครบ 100% (`count(*) = count(embedding)`)
- [ ] `idx_tickets_embedding` ถูกสร้างหลัง backfill เสร็จ (ไม่ใช่ก่อน)
- [ ] ค้นหาด้วยคำถามภาษาธรรมชาติใน PostgreSQL ได้ผลลัพธ์ที่เกี่ยวข้องจริง เรียงตามระยะห่างจากน้อยไปมาก
- [ ] `device_embedding` และ `circuit_embedding` ถูกสร้างครบทั้งสอง index ใน Neo4j และมีสถานะ `ONLINE`
- [ ] `MATCH (n) WHERE n.embedding IS NOT NULL RETURN count(n)` ได้ 45 (10 Device + 35 Circuit)
- [ ] `db.index.vector.queryNodes` คืนผลลัพธ์ที่สมเหตุสมผล (อุปกรณ์ประเภทเดียวกันควรมีคะแนนใกล้กัน)

---

## โบนัส (ถ้าเวลาเหลือ)

1. **เทียบ keyword กับ semantic** — ค้นคำว่า `หลุด` ด้วย `LIKE '%หลุด%'` เทียบกับผลจากขั้นที่ 5 ต่างกันมากน้อยเพียงใด
2. **ลองใช้ `vector_l2_ops` แทน `vector_cosine_ops`** ตอนสร้าง index ใหม่ แล้วดูว่าอันดับผลลัพธ์เปลี่ยนไปอย่างไร
3. **เดินกราฟต่อจากผลค้นหา** — จากผลของขั้นที่ 7 เขียน Cypher ต่ออีกหนึ่ง `MATCH` เพื่อหาว่า `CR-BKK-02` เชื่อมกับ `Circuit` ใดบ้าง ในคำสั่งเดียวกับที่ query vector — นี่คือหลักฐานของหัวข้อ "ทำไม Neo4j ต้องมีของตัวเอง" ด้านบน

<details>
<summary>หากใช้เวลาเกิน 15 นาทีแล้วยังไม่สำเร็จ คลิกเพื่อดูเฉลย</summary>

- DDL ล้วน (ไม่มี Python) ของฝั่ง PostgreSQL อยู่ที่ `make lab1-solution` ([`scripts/lab/lab1_solution_vector.sql`](../../scripts/lab/lab1_solution_vector.sql))
- โค้ด backfill อ้างอิงเต็มรูปแบบ: `make embed-tickets` (PostgreSQL, [`scripts/embed_tickets.py`](../../scripts/embed_tickets.py)) และ `make embed-devices` (Neo4j, [`scripts/embed_devices.py`](../../scripts/embed_devices.py))
- ถ้า embedding endpoint ต่อไม่ติดกลางคัน ใช้สองคำสั่งข้างบนแทนสคริปต์ของตัวเองได้เลย ไม่ต้องรอ

</details>

---

## สิ่งที่ต้องส่ง

สคริปต์ backfill ของตัวเองทั้งสองฝั่ง (`pg_backfill_tickets.py`, `neo4j_backfill_profiles.py`) + ผลลัพธ์การค้นหาจริงจากทั้ง PostgreSQL และ Neo4j

---

## ต่อไป

→ [Module 2: Embeddings กับ OpenSearch](03-module2-embeddings-opensearch.md) — ฐานข้อมูลตัวที่ 3 ที่เก็บ vector ได้ และเป็นตัวที่ production เลือกใช้เป็นหลัก
