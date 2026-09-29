# Lab · Vector ใน PostgreSQL

**10:30 – 11:05** (35 นาที) · ต่อจาก Module 1

---

## เป้าหมาย

ดำเนินการสร้าง pipeline ของ semantic search ครบวงจรด้วยตนเองใน PostgreSQL — ตั้งแต่การเพิ่ม column, สร้าง embedding, backfill, สร้าง index ไปจนถึงการค้นหา

ระบบในขณะนี้ **มี embedding พร้อมใช้งานอยู่แล้ว** ขั้นตอนแรกของ lab นี้คือการลบข้อมูลดังกล่าวออก เพื่อให้ผู้เรียนได้สร้างขึ้นใหม่ด้วยตนเอง

ต่อด้วย [Lab: Vector ใน Neo4j](03-lab-neo4j-vectors.md) ที่ใช้หลักการเดียวกันนี้ แต่ในฐานข้อมูลกราฟซึ่งเก็บ vector คนละแบบ

---

## ขั้นที่ 0 · ตรวจสอบข้อมูลเดิมก่อนลบ

เปิด pgAdmin ([http://localhost:5050](http://localhost:5050)) รัน:

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

หมายเหตุ: `make lab1-reset` ลบ vector ทั้งใน **PostgreSQL และ Neo4j** พร้อมกันในคำสั่งเดียว (Neo4j จะลบเองอีกครั้งใน [Lab: Vector ใน Neo4j](03-lab-neo4j-vectors.md)) หากต้องการรันเพียงคำสั่งเดียวแทนการเปิด pgAdmin สามารถใช้คำสั่งนี้ได้เช่นกัน

ลองถามคำถามเดิมอีกครั้ง — ระบบจะตอบว่ายังไม่มี embedding

---

**เหตุผลที่ต้องใช้ 1024** — ต้องตรงกับมิติของโมเดล หากกำหนดผิด `INSERT` จะเกิด error ทุกแถว

```powershell
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

เขียน `my_embed.py` ขึ้นเอง (วางไว้ที่ root ของโปรเจกต์) โดยมีโครงสร้างประมาณนี้ — **ทุกค่าตั้งต้นต้องอ่านจาก `.env`** ไม่ hardcode:

```python
import os
import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv()  # อ่าน .env จาก working directory ปัจจุบัน

PG_DSN = os.getenv("PG_ADMIN_DSN", "postgresql://mpls:mpls_dev_password@localhost:5432/mplsdb")
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

with psycopg.connect(PG_DSN) as conn:
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

**ผลลัพธ์ที่ควรเห็น** (รันจริงตอนเตรียมเอกสารนี้):

```
32/117
64/117
96/117
117/117
```

### ข้อผิดพลาดที่พบบ่อย 3 ประการ

| ข้อผิดพลาด | ผลที่เกิดขึ้น |
|---|---|
| ไม่เรียง `data` ตาม `index` | vector ไปสลับ ticket กัน — **ค้นแล้วได้ผลลัพธ์ผิดโดยไม่มี error แจ้งเตือน** |
| ส่งคำขอทีละแถว | 117 แถวใช้เวลาหลายนาที แทนที่จะเป็นเพียงไม่กี่วินาที |
| embed เฉพาะ `title` | ค้นเจอน้อยลงมาก เพราะรายละเอียดอยู่ใน `description` |

---

## ขั้นที่ 4 · สร้าง index

```sql
CREATE INDEX idx_tickets_embedding ON tickets
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

**ควรสร้าง index หลัง backfill เสมอ** — ดัชนี HNSW ที่สร้างบนตารางว่างแล้วจึงเติมข้อมูลทีละแถวภายหลัง จะได้กราฟที่มีคุณภาพต่ำกว่าและทำงานช้ากว่า

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

เขียน `cosine.py` ขึ้นเองเพื่อทดสอบ semantic search ครบวงจร (แปลงคำถามเป็น embedding แล้วค้นด้วย `<=>` ใน Postgres โดยตรง) — **อ่านค่าจาก `.env` เหมือน `my_embed.py`** ไม่ hardcode key:

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

**ผลลัพธ์ที่ควรเห็น** สำหรับคำค้น `"ลูกค้าบ่นว่าอินเทอร์เน็ตหลุดบ่อย"` (รันจริงตอนเตรียมเอกสารนี้):

```
ความยาวมิติเวกเตอร์: 1024
0.2947  TK-25-00001  อินเทอร์เน็ตหลุดเป็นช่วงๆ ตั้งแต่เมื่อวาน
0.3624  TK-25-00005  เน็ตหลุดซ้ำ เคสเดิมที่เคยแจ้งไว้
0.3717  TK-25-00002  เน็ตกระตุกเป็นช่วง ใช้งานไม่ต่อเนื่อง
0.4159  TK-25-00004  หลุดบ่อยช่วงบ่าย
0.5052  TK-25-00015  latency สูงผิดปกติช่วงเย็น
```

ticket แถวบนสุดควรอยู่ในหมวด `intermittent`/`link_down` ที่เกี่ยวข้องกับปัญหาเน็ตหลุดโดยตรง หากได้ผลลัพธ์ที่ไม่เกี่ยวข้องเลย ให้ตรวจสอบว่า backfill เสร็จสมบูรณ์จริงหรือยัง (ดู query แรกของขั้นตอนนี้)

**หมายเหตุ**: ตัวเลข distance ที่ได้จริงอาจต่างจากตัวอย่างข้างต้นเล็กน้อยในแต่ละครั้งที่ backfill ใหม่ (embedding API ไม่ deterministic 100% ทุกครั้งที่เรียก) — ที่ต้องเหมือนกันเสมอคือ `TK-25-00001` ติดอันดับ 1 และ ticket หมวด `intermittent` ทั้งหมดต้องติดกลุ่มอันดับต้นๆ ไม่ใช่ตัวเลขทศนิยมที่เป๊ะเหมือนกันทุกรอบ

---

## เกณฑ์ผ่าน

- [ ] `SELECT count(embedding) FROM tickets` = จำนวน ticket ทั้งหมด
- [ ] มี HNSW index บน `tickets.embedding`
- [ ] ค้นคำว่า *"เน็ตหลุดบ่อย"* แล้วได้ ticket ประเภท `intermittent` ติดอันดับต้น

---

## โบนัส

1. **เทียบ keyword กับ semantic** — ค้นคำว่า `circuit drop` ด้วย `LIKE` เทียบกับ vector ผลต่างกันมากน้อยเพียงใด
2. **ลองใช้ `vector_l2_ops` แทน cosine** แล้วดูว่าอันดับเปลี่ยนไปอย่างไร
3. **วัดเวลา** — เทียบ query ก่อนและหลังสร้าง index

<details>
<summary>หากใช้เวลาเกิน 10 นาทีแล้วยังไม่สำเร็จ คลิกเพื่อดูเฉลย</summary>

- DDL เต็มอยู่ที่ `scripts/lab/lab1_solution_vector.sql` (`make lab1-solution`)
- โค้ด backfill อ้างอิงอยู่ที่ `scripts/embed_tickets.py` (`make embed-tickets`)
- ถ้า endpoint ต่อไม่ได้ ให้ใช้ `LLM_MODEL_FAST` และตรวจ VPN

</details>

---

## สิ่งที่ต้องส่ง

`my_embed.py` และ `cosine.py` ที่เขียนขึ้นเอง พร้อมผลลัพธ์ query ในขั้นที่ 5

---

## ต่อไป

→ [Lab: Vector ใน Neo4j](03-lab-neo4j-vectors.md)
