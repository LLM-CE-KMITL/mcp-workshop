# Lab 1 · สร้าง Vector Column ด้วยตัวเอง

**09:50 – 10:30** (40 นาที) · ต่อจาก Module 1

---

## เป้าหมาย

ทำ pipeline ของ semantic search ครบวงจรด้วยมือตัวเอง: เพิ่ม column → สร้าง embedding → backfill → สร้าง index → ค้นหา

ระบบตอนนี้ **มี embedding พร้อมใช้อยู่แล้ว** ขั้นแรกของ lab คือลบมันทิ้ง เพื่อให้ได้สร้างเอง

---

## ขั้นที่ 0 · ดูของเดิมก่อนลบ

เปิด pgAdmin (http://localhost:5050) รัน:

```sql
SELECT count(*) AS total, count(embedding) AS embedded FROM tickets;
```

ลอง semantic search ที่ Chainlit: *"เคยมีเคสเน็ตหลุดเป็นช่วงๆ ไหม"* — ทำงานได้

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

คำสั่งข้างบนนี้ลบ vector ทั้งใน **PostgreSQL และ Neo4j** (ตรงกับที่ `make lab1-reset` ทำให้อัตโนมัติ ถ้าอยากรันทีเดียวแทนการเปิด 2 หน้าต่างก็ใช้คำสั่งนั้นได้เลย)

ลองถามคำถามเดิมอีกครั้ง — ระบบจะตอบว่ายังไม่มี embedding

---

**ทำไมต้อง 1024** — ต้องตรงกับมิติของโมเดล ถ้าใส่ผิด `INSERT` จะ error ทุกแถว

```bash
$headers = @{
    "Authorization" = "Bearer ***Your Key***"
    "Content-Type" = "application/json"
}
$body = '{"model":"baai/bge-m3","input":["test"]}'
(Invoke-RestMethod -Uri "https://openrouter.ai/api/v1/embeddings" -Method Post -Headers $headers -Body $body).data[0].embedding.Count
```

## ขั้นที่ 2 · เพิ่ม column

```sql
ALTER TABLE tickets ADD COLUMN embedding vector(1024);
```

ตรวจสอบว่า column ถูกสร้างจริง (ควรเห็น 1 แถว, `udt_name` เป็น `vector`):
```sql
SELECT column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_name = 'tickets' AND column_name = 'embedding';
```

ตอนนี้ column ยังว่างเปล่า (ยังไม่ backfill) — ยืนยันด้วย:
```sql
SELECT count(*) AS total, count(embedding) AS embedded FROM tickets;
```
ควรได้ `embedded = 0` (ถ้าไม่ใช่ 0 แปลว่า ขั้นที่ 1 ลบไม่หมด ย้อนกลับไปเช็คก่อน)

---

## ขั้นที่ 3 · สร้าง embedding และ backfill

เขียน `my_embed.py` เอง (วางไว้ที่ root ของโปรเจกต์) โครงประมาณนี้ — **ทุกค่าตั้งต้นอ่านจาก `.env`** ไม่ hardcode:

```python
import os
import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv()  # อ่าน .env จาก working directory ปัจจุบัน

# ทุกตัวแปรอ่านจาก .env เป็นค่าเริ่มต้น - ใช้ค่าเดียวกับที่ MCP server/seeder ใช้จริง
# PG_ADMIN_DSN ไม่มีใน .env.example เพราะเป็น user เต็มสิทธิ์ (เขียนได้) ต่างจาก
# PG_DSN ปกติที่เป็น mcp_reader (read-only) - ใส่เพิ่มเองใน .env ถ้าต้องการ หรือปล่อย
# เป็น default นี้ก็ได้เพราะ mpls คือ user เต็มสิทธิ์อยู่แล้วตาม docker-compose.yml
PG = os.getenv("PG_ADMIN_DSN", "postgresql://mpls:mpls_dev_password@localhost:5432/mplsdb")
EMB = os.getenv("EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/") + "/embeddings"
MODEL = os.getenv("EMBEDDING_MODEL", "baai/bge-m3")
API_KEY = os.getenv("LLM_API_KEY", "")

def embed_batch(texts: list[str]) -> list[list[float]]:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "HTTP-Referer": "http://localhost",
        "X-Title": "MCP Workshop"
    }
    
    r = httpx.post(
        EMB, 
        json={"model": MODEL, "input": texts},
        headers=headers, 
        timeout=60
    )
    r.raise_for_status()
    data = sorted(r.json()["data"], key=lambda d: d["index"])   # อย่าลืมเรียงลำดับ
    return [d["embedding"] for d in data]

with psycopg.connect(PG) as conn:
    cur = conn.cursor()
    cur.execute("SELECT ticket_id, title, description FROM tickets ORDER BY ticket_id")
    rows = cur.fetchall()

    BATCH = 32           # ยิงทีละ 32 แถว
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i+BATCH]
        vecs = embed_batch([f"{t}\n\n{d}" for _, t, d in chunk])
        for (tid, _, _), v in zip(chunk, vecs):
            # แปลง vector เป็น string สำหรับใส่ใน postgres
            vector_str = "[" + ",".join(map(str, v)) + "]"
            cur.execute("UPDATE tickets SET embedding = %s::vector WHERE ticket_id = %s",
                        (vector_str, tid))
        conn.commit()
        print(f"{i+len(chunk)}/{len(rows)}")
```

### วิธีรัน

```bash
uv run python my_embed.py
```

ต้องรันจาก root ของโปรเจกต์ (ที่มีไฟล์ `.env` อยู่) ไม่งั้น `load_dotenv()` จะหา `.env` ไม่เจอ และ `API_KEY` จะว่างเปล่า ทำให้ OpenRouter ตอบ `401 Unauthorized`

### 3 จุดที่คนพลาดบ่อย

| พลาด | ผลที่เกิด |
|---|---|
| ไม่เรียง `data` ตาม `index` | vector ไปสลับ ticket กัน — **ค้นแล้วผิดโดยไม่มี error** |
| ยิงทีละแถว | 120 แถวใช้เวลาหลายนาที แทนที่จะเป็นไม่กี่วินาที |
| embed แค่ `title` | ค้นเจอน้อยลงมาก เพราะรายละเอียดอยู่ใน `description` |

---

## ขั้นที่ 4 · สร้าง index

```sql
CREATE INDEX idx_tickets_embedding ON tickets
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

**สร้าง index หลัง backfill เสมอ** — HNSW ที่สร้างบนตารางว่างแล้วค่อยเติมทีละแถวจะได้กราฟที่คุณภาพแย่กว่าและช้ากว่า

ตรวจสอบว่า index ถูกสร้างจริง (ควรเห็น 1 แถว, `indexdef` มีคำว่า `hnsw`):
```sql
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename = 'tickets' AND indexname = 'idx_tickets_embedding';
```

---

## ขั้นที่ 5 · ทดสอบ

ตอนนี้ backfill เสร็จแล้ว ตัวเลขนี้ควรเปลี่ยนจาก `embedded = 0` (ที่เห็นในขั้นที่ 2) เป็น **`embedded = total`**:
```sql
SELECT count(*) AS total, count(embedding) AS embedded FROM tickets;
```

เขียน `cosine.py` เองเพื่อทดสอบ semantic search ครบวงจร (embed คำถาม → ค้นด้วย `<=>` ใน Postgres โดยตรง) — **อ่านค่าจาก `.env` เหมือน `my_embed.py`** ไม่ hardcode key:

```mermaid
flowchart LR
    A["คำถามภาษาไทย<br/>'ลูกค้าบ่นว่าอินเทอร์เน็ตหลุดบ่อย'"] --> B["OpenRouter<br/>/embeddings API<br/>(baai/bge-m3)"]
    B --> C["query vector<br/>1024 มิติ"]
    C --> D["PostgreSQL<br/>ORDER BY embedding &lt;=&gt; query_vec"]
    D --> E["ticket 5 อันดับแรก<br/>เรียงตาม distance (น้อย = ใกล้)"]
```

```python
import os
import psycopg
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

EMB_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1")
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "baai/bge-m3")
PG = os.getenv("PG_ADMIN_DSN", "postgresql://mpls:mpls_dev_password@localhost:5432/mplsdb")

client = OpenAI(base_url=EMB_BASE_URL, api_key=os.getenv("LLM_API_KEY", ""))

def embed_batch(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=EMB_MODEL, input=texts)
    return [item.embedding for item in response.data]

# ดูค่าที่ดึงมาจาก .env จริง ๆ ก่อนรัน - ช่วยดีบั๊กเวลาผลลัพธ์ไม่ตรงที่คิดไว้
print(f"EMBEDDING_BASE_URL = {EMB_BASE_URL}")
print(f"EMBEDDING_MODEL    = {EMB_MODEL}")
print(f"PG_ADMIN_DSN       = {PG}")
print(f"LLM_API_KEY        = {'(ตั้งค่าแล้ว)' if os.getenv('LLM_API_KEY') else '(ว่างเปล่า! เช็ค .env)'}")

print("กำลังแปลงคำถามเป็น embedding...")
q = embed_batch(["ลูกค้าบ่นว่าอินเทอร์เน็ตหลุดบ่อย"])[0]
print("ความยาวมิติเวกเตอร์:", len(q))  # ควรจะได้ 1024

# `<=>` คือ cosine distance ใน pgvector - ยิ่งน้อยยิ่งใกล้
query_vec = "[" + ",".join(map(str, q)) + "]"
with psycopg.connect(PG) as conn:
    cur = conn.cursor()
    cur.execute(
        """SELECT ticket_id, title, embedding <=> %s::vector AS distance
           FROM tickets
           ORDER BY embedding <=> %s::vector
           LIMIT 5""",
        (query_vec, query_vec),
    )
    for ticket_id, title, distance in cur.fetchall():
        print(f"{distance:.4f}  {ticket_id}  {title}")
```

รัน:
```bash
uv run python cosine.py
```

ticket แถวบนสุดควรเป็นหมวด `intermittent`/`link_down` ที่พูดถึงเน็ตหลุดจริง ๆ ถ้าได้ผลลัพธ์ที่ไม่เกี่ยวข้องเลย ให้เช็คว่า backfill เสร็จสมบูรณ์จริงหรือยัง (ดู query แรกของขั้นนี้)

---

## ขั้นที่ 6 · ทำ Neo4j ด้วย

index เดิมถูกลบไปแล้วตั้งแต่ขั้นที่ 1 — สร้างใหม่ให้รองรับ 1024 มิติ:

```cypher
CREATE VECTOR INDEX device_embedding IF NOT EXISTS
FOR (d:Device) ON (d.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};
```

แล้ว backfill `d.profile_text` เข้าไปด้วยสคริปต์อ้างอิง (โค้ดตัวอย่างอยู่ใน `docker/seeder/seed_neo4j.py`):

```bash
uv run python scripts/embed_devices.py
```

ค้นหา:

```cypher
MATCH (d:Device) 
WHERE d.embedding IS NOT NULL
WITH d.embedding AS mock_vec LIMIT 1
CALL db.index.vector.queryNodes('device_embedding', 3, mock_vec)
YIELD node, score 
RETURN node.device_id, score
```

---

## เกณฑ์ผ่าน

- [ ] `SELECT count(embedding) FROM tickets` = จำนวน ticket ทั้งหมด
- [ ] มี HNSW index บน `tickets.embedding`
- [ ] ค้นคำว่า *"เน็ตหลุดบ่อย"* แล้วได้ ticket ประเภท `intermittent` ติดอันดับต้น
- [ ] Neo4j มี vector index และทุก `:Device` มี `embedding`
- [ ] Chainlit ตอบคำถาม semantic ได้อีกครั้ง

---

## โบนัส

1. **เทียบ keyword กับ semantic** — ค้นคำว่า `circuit drop` ด้วย `LIKE` เทียบกับ vector ผลต่างกันแค่ไหน
2. **ลองใช้ `vector_l2_ops` แทน cosine** แล้วดูว่าอันดับเปลี่ยนไปอย่างไร
3. **วัดเวลา** — เทียบ query ก่อนและหลังสร้าง index

<details>
<summary>ติดเกิน 10 นาทีแล้วกดดู</summary>

- DDL เต็มอยู่ที่ `scripts/lab/lab1_solution_vector.sql` (`make lab1-solution`)
- โค้ด backfill อ้างอิงอยู่ที่ `scripts/embed_tickets.py` (`make embed-tickets`)
- ถ้า endpoint ต่อไม่ได้ ให้ใช้ `LLM_MODEL_FAST` และตรวจ VPN
</details>

---

## สิ่งที่ต้องส่ง

`my_embed.py` ของตัวเอง + ผลลัพธ์ query ขั้นที่ 5
