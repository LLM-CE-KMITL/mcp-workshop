# Lab · Vector ใน PostgreSQL และ Neo4j

**10:30 – 11:30** (60 นาที) · เป้าหมาย: สร้าง vector column และ vector index ให้ทำงานได้จริงด้วยมือตัวเองในสองฐานข้อมูล ก่อนที่ Module 2 จะไปทำแบบเดียวกันกับ OpenSearch

---

## เป้าหมาย

ทำ pipeline ของ semantic search ครบวงจรด้วยมือตัวเอง: เพิ่ม column/index → สร้าง embedding → backfill → ค้นหา — ในสองฐานข้อมูลที่มีวิธีเก็บ vector ต่างกัน (คอลัมน์ใน PostgreSQL เทียบกับ property ของ node ใน Neo4j)

ระบบตอนนี้ **มี embedding พร้อมใช้งานอยู่แล้ว** ทั้งสองฝั่ง ขั้นแรกของ lab คือลบมันทิ้ง เพื่อให้ได้สร้างเอง

---

## ขั้นที่ 0 · ดูของเดิมก่อนลบ

```sql
SELECT count(*) AS total, count(embedding) AS embedded FROM tickets;
```

```cypher
MATCH (n) WHERE n.embedding IS NOT NULL RETURN labels(n)[0] AS label, count(n) AS n;
```

ลองถามคำถามที่ต้องใช้ semantic search ผ่าน Chainlit หรือ MCP Inspector ก่อน — ควรทำงานได้ปกติ

---

## ขั้นที่ 1 · ลบทิ้ง

```bash
make lab1-reset
```

คำสั่งนี้รัน [`scripts/lab/lab1_reset_vector.sql`](../../scripts/lab/lab1_reset_vector.sql) (ลบ column `embedding` และ index ใน PostgreSQL) และ [`scripts/lab/lab1_reset_vector.cypher`](../../scripts/lab/lab1_reset_vector.cypher) (ลบ vector index และ property `embedding` ของทุก node ใน Neo4j) พร้อมกันทั้งสองฐานข้อมูล — ยืนยันผลได้จากตัวเลขที่คำสั่งพิมพ์ออกมา ควรเห็น `0 rows` และ `nodes_with_embedding = 0`

ลองถามคำถามเดิมอีกครั้ง — ระบบควรตอบว่ายังไม่มี embedding หรือค้นไม่เจอ

---

## ขั้นที่ 2 · PostgreSQL — เพิ่ม column แล้ว backfill

**ทำไมต้อง 1024** — ต้องตรงกับมิติของโมเดล embedding (`EMBEDDING_DIM` ใน `.env`) ถ้าใส่ผิด `INSERT`/`UPDATE` จะ error ทุกแถว

```sql
ALTER TABLE tickets ADD COLUMN embedding vector(1024);
```

เขียนสคริปต์ backfill ของตัวเอง (โครงเดียวกับที่ [`scripts/embed_tickets.py`](../../scripts/embed_tickets.py) ใช้จริง — เรียก `EMBEDDING_BASE_URL/embeddings` แบบ OpenAI-compatible, เรียงผลตาม `index` ก่อนจับคู่กับแถวเสมอเพราะ API ไม่รับประกันลำดับ, ยิงเป็น batch ไม่ใช่ทีละแถว):

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

**ผลลัพธ์ที่ควรเห็น** (รันจริงตอนเตรียมเอกสารนี้):

```
Embedding 117 tickets with baai/bge-m3
    32/117
    64/117
    96/117
    117/117

  Done: 117/117 tickets have embeddings
```

สร้าง index **หลัง**จาก backfill เสร็จเท่านั้น (HNSW ที่สร้างบนตารางว่างแล้วค่อยเติมทีละแถวจะได้กราฟที่คุณภาพแย่กว่า):

```sql
CREATE INDEX idx_tickets_embedding ON tickets
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

ทดสอบค้นหาจริง — embed คำถามด้วยฟังก์ชันเดียวกับด้านบน แล้วค้นด้วย `<=>` (cosine distance ใน pgvector ยิ่งน้อยยิ่งใกล้):

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

---

## ขั้นที่ 3 · Neo4j — สร้าง vector index แล้ว backfill

Neo4j เก็บ vector เป็น **property ของ node โดยตรง** ไม่ใช่คอลัมน์แยก และต้องสร้าง index สองตัวแยกกันเพราะมีสอง label ที่ต้องการ semantic search (`Device` และ `Circuit`):

```cypher
CREATE VECTOR INDEX device_embedding IF NOT EXISTS
FOR (d:Device) ON (d.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};

CREATE VECTOR INDEX circuit_embedding IF NOT EXISTS
FOR (c:Circuit) ON (c.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};
```

ข้อความที่ต้อง embed ไม่ใช่ทั้ง node แต่เป็นฟิลด์ `profile_text` ที่ seed ไว้ให้แล้ว — ดูตัวอย่างจริง: `"CR-BKK-01 is a core router carrying backbone transit between sites. Located at site BKK. Management address 10.10.0.1. Interfaces: Hu0/0/0/0, Hu0/0/0/1, Hu0/0/0/2."`

เขียนสคริปต์ backfill (โครงเดียวกับ [`scripts/embed_devices.py`](../../scripts/embed_devices.py) — วนทั้งสอง label ในลูปเดียว เพราะ logic เหมือนกันทุกประการ ต่างแค่ label):

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

**ผลลัพธ์ที่ควรเห็น**:

```
embedded 10 Device nodes
embedded 35 Circuit nodes

45 nodes now carry embeddings
```

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
- [ ] `device_embedding` และ `circuit_embedding` ถูกสร้างครบทั้งสอง index ใน Neo4j
- [ ] `MATCH (n) WHERE n.embedding IS NOT NULL RETURN count(n)` ได้ 45 (10 Device + 35 Circuit)
- [ ] `db.index.vector.queryNodes` คืนผลลัพธ์ที่สมเหตุสมผล (อุปกรณ์ประเภทเดียวกันควรมีคะแนนใกล้กัน)

---

## ถ้า embedding endpoint ล่มกลางคัน

โปรเจกต์นี้มีคำสั่งสำรองให้ใช้ต่อได้โดยไม่ต้องรอ (อ่านโค้ดจริงได้ที่ [`scripts/embed_tickets.py`](../../scripts/embed_tickets.py) และ [`scripts/embed_devices.py`](../../scripts/embed_devices.py) — เป็นเฉลยเต็มรูปแบบ อย่าเปิดจนกว่าจะลองเขียนเองก่อน):

```bash
make embed-tickets    # backfill ฝั่ง PostgreSQL
make embed-devices    # backfill ฝั่ง Neo4j (Device + Circuit)
```

DDL ล้วน (ไม่มี Python) ของฝั่ง PostgreSQL อยู่ที่ `make lab1-solution` ([`scripts/lab/lab1_solution_vector.sql`](../../scripts/lab/lab1_solution_vector.sql))

---

## สิ่งที่ต้องส่ง

สคริปต์ backfill ของตัวเองทั้งสองฝั่ง + ผลลัพธ์การค้นหาจริงจากทั้ง PostgreSQL และ Neo4j

---

## ต่อไป

→ [Module 2: Embeddings กับ OpenSearch](03-module2-embeddings-opensearch.md) — ฐานข้อมูลตัวที่ 3 ที่เก็บ vector ได้ และเป็นตัวที่ production เลือกใช้เป็นหลัก
