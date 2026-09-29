# Module 2 · Embeddings กับ OpenSearch

**10:45 – 12:00** (75 นาที) · เป้าหมาย: เข้าใจว่า embedding แปลงข้อความเป็นเวกเตอร์ตัวเลขที่บันทึก "ความหมาย" ไว้ได้อย่างไร และลงมือสร้าง pipeline บันทึก + ค้นหาเวกเตอร์จริงบน OpenSearch ด้วยตัวเอง

---

## 1. จาก Token สู่ Vector: Embedding คืออะไร

Module 1 แสดงให้เห็นว่าโมเดลมองข้อความเป็นลำดับ token Embedding คือขั้นถัดไป: แปลงข้อความทั้งก้อน (ไม่ว่าจะสั้นแค่ไหน) ให้กลายเป็นเวกเตอร์ตัวเลขความยาวคงที่หนึ่งเส้น ซึ่งตำแหน่งของเวกเตอร์ในปริภูมิหลายมิตินั้นสะท้อน "ความหมาย" ของข้อความ — ข้อความที่ความหมายใกล้กันจะมีเวกเตอร์อยู่ใกล้กัน แม้จะใช้คำคนละคำกันเลยก็ตาม

นี่คือความต่างสำคัญจากการค้นหาแบบ keyword (เช่น trigram index `idx_tickets_title_trgm` ที่มีอยู่แล้วในตาราง `tickets`): keyword search หาคำที่ "เขียนคล้ายกัน" ส่วน semantic search ด้วย embedding หาข้อความที่ "หมายถึงเรื่องเดียวกัน" แม้ประโยคจะไม่มีคำร่วมกันเลย เช่น "เน็ตหลุดเป็นพัก ๆ" กับ "circuit flapping ทุกสิบนาที"

โปรเจกต์นี้ใช้โมเดล embedding ตัวเดียวกันตลอดทั้งระบบ กำหนดไว้ใน `.env.example`:

| ตัวแปร | ค่า | ความหมาย |
|---|---|---|
| `EMBEDDING_BASE_URL` | `https://openrouter.ai/api/v1` | endpoint แบบ OpenAI-compatible |
| `EMBEDDING_MODEL` | `baai/bge-m3` | โมเดล embedding |
| `EMBEDDING_DIM` | `1024` | ความยาวเวกเตอร์ที่โมเดลนี้คืนกลับมา |

ทุกจุดในระบบที่ต้อง embed ข้อความ เรียก endpoint เดียวกันด้วยรูปแบบเดียวกันเสมอ (ดูตัวอย่างจริงใน `docker/seeder/embed.py`):

```python
httpx.post(
    f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
    json={"model": EMBEDDING_MODEL, "input": texts},   # input เป็น list รับได้หลายข้อความในคำขอเดียว
    headers={"Authorization": f"Bearer {LLM_API_KEY}"},
)
```

**ข้อควรระวังที่ `docker/seeder/embed.py` เจอมาแล้วจริง**: API ไม่ได้สัญญาว่าจะคืนผลลัพธ์ตามลำดับที่ส่งเข้าไป ต้องเรียงตาม `data[i]["index"]` เองเสมอก่อนจับคู่กับข้อความต้นทาง มิฉะนั้นเวกเตอร์จะไปผูกกับข้อความผิดแถวโดยไม่มี error ใด ๆ แจ้งเตือน

---

## 2. วัดความ "ใกล้" กันของเวกเตอร์: cosine similarity และ kNN

เมื่อมีเวกเตอร์แล้ว การค้นหา "สิ่งที่คล้ายกัน" คือการหาเวกเตอร์ที่อยู่ใกล้กันที่สุดในปริภูมินั้น วิธีวัดที่นิยมที่สุดสำหรับ text embedding คือ **cosine similarity** (มุมระหว่างเวกเตอร์สองเส้น ไม่สนใจขนาด) ยิ่งมุมแคบยิ่งคล้ายกัน

การค้นแบบนี้คือ **kNN (k-Nearest Neighbors)**: หาเวกเตอร์ k ตัวที่ใกล้กับเวกเตอร์คำค้นมากที่สุด แทนที่จะหาคำที่ตรงกันแบบ exact match

โปรเจกต์นี้มี vector search อยู่แล้วถึง 3 ที่ (ดูภาพรวมที่ `day0/01-architecture.md` หัวข้อ 2) — ตาราง `tickets` ใน PostgreSQL เองก็มีคอลัมน์ `embedding vector(1024)` พร้อม HNSW index (`idx_tickets_embedding`) ประกาศไว้แล้วใน `docker/postgres/init/02_schema.sql.template` โมดูลนี้เจาะเฉพาะฝั่ง **OpenSearch** ซึ่งเป็นฐานที่สามในสถาปัตยกรรมนั้น

---

## 3. OpenSearch เป็น Vector Store: `knn_vector`

OpenSearch รองรับ vector search ผ่านชนิดฟิลด์ `knn_vector` ในโปรเจกต์นี้มี index ที่ใช้ pattern นี้อยู่แล้วสำหรับเอกสาร runbook/config (`network-docs`) — ดู mapping จริงที่ `docker/opensearch/seed/doc_index_template.json`:

```json
"embedding": {
  "type": "knn_vector",
  "dimension": 1024,
  "method": {
    "name": "hnsw",
    "space_type": "cosinesimil",
    "engine": "lucene",
    "parameters": { "ef_construction": 128, "m": 16 }
  }
}
```

ส่วนประกอบสำคัญของ mapping นี้:

| ส่วน | ความหมาย |
|---|---|
| `dimension` | ต้องตรงกับ `EMBEDDING_DIM` เป๊ะ ไม่ตรงแล้ว index จะปฏิเสธการเขียนข้อมูล |
| `method.name: hnsw` | อัลกอริทึมสร้างกราฟเพื่อนบ้านสำหรับค้นหาแบบประมาณ (approximate) เร็วกว่า exact search มากเมื่อข้อมูลเยอะ |
| `space_type: cosinesimil` | ใช้ cosine similarity เป็นตัววัดระยะ ตรงกับที่ระบุในหัวข้อ 2 |
| `ef_construction` / `m` | พารามิเตอร์ปรับสมดุลความแม่นยำกับความเร็วตอนสร้าง index |

`network-docs` เก็บ runbook และ device config ที่ถูก chunk แล้ว (ดู pipeline จริงที่ `docker/seeder/seed_opensearch.py`) โมดูลนี้จะสร้าง index แบบเดียวกันแต่สำหรับ **ticket** โดยตรง ซึ่งยังไม่มีอยู่ในระบบวันนี้ — เป็นสิ่งที่ต้องสร้างขึ้นเองใน Lab ด้านล่าง

```mermaid
flowchart LR
    PG[("PostgreSQL<br/>tickets")] -->|"title + description"| EMB["Embedding endpoint<br/>baai/bge-m3"]
    EMB -->|"vector 1024 มิติ"| IDX["OpenSearch index ใหม่<br/>knn_vector"]
    Q["คำค้นภาษาธรรมชาติ"] --> EMB2["Embedding endpoint"]
    EMB2 -->|"query vector"| KNN{"kNN query"}
    IDX --> KNN
    KNN --> R["ticket ที่ใกล้เคียงที่สุด<br/>เรียงตามคะแนน"]
```

---

## Lab: บันทึก Ticket ลง OpenSearch แล้วค้นหาด้วย kNN

### เป้าหมาย

สร้าง index ใหม่สำหรับ ticket บน OpenSearch, embed ticket จริงจาก PostgreSQL, บันทึกเข้า index, แล้วค้นหาด้วยคำถามภาษาธรรมชาติผ่าน kNN query

### สิ่งที่ให้มา

- ตาราง `tickets` (อ่านผ่าน `PG_DSN` / บัญชี read-only `mcp_reader` — งานนี้ทำแค่ `SELECT` เท่านั้น)
- Endpoint embedding และตัวแปรใน `.env.example`: `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`
- `OPENSEARCH_URL` ใน `.env.example` (ค่าเริ่มต้น `http://localhost:9200`)
- mapping style อ้างอิงจาก `docker/opensearch/seed/doc_index_template.json` (หัวข้อ 3 ด้านบน)
- ไลบรารี `opensearchpy` (มีอยู่แล้วใน `pyproject.toml`)

### ขั้นตอน

บันทึกโค้ดต่อไปนี้เป็น `ticket_opensearch_lab.py` ที่ root ของโปรเจกต์:

```python
"""Lab Module 2: index tickets into OpenSearch and search them with kNN."""
from __future__ import annotations

import os

import httpx
import psycopg
from dotenv import load_dotenv
from opensearchpy import OpenSearch, helpers

load_dotenv()

PG_DSN = os.getenv(
    "PG_DSN", "postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb"
)
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "baai/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed")

# ชื่อ index ของ lab นี้โดยเฉพาะ แยกจาก network-docs / network-logs ที่มีอยู่แล้ว
TICKET_INDEX = "tickets-lab"


def embed_many(texts: list[str]) -> list[list[float]]:
    """เรียก embedding endpoint แบบเดียวกับที่ docker/seeder/embed.py ใช้จริง"""
    response = httpx.post(
        f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
        json={"model": EMBEDDING_MODEL, "input": texts},
        headers={"Authorization": f"Bearer {LLM_API_KEY}"},
        timeout=60,
    )
    response.raise_for_status()
    # ต้องเรียงตาม index เอง - API ไม่รับประกันลำดับ (บทเรียนจาก embed.py)
    ordered = sorted(response.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in ordered]


def ensure_index(client: OpenSearch) -> None:
    if client.indices.exists(index=TICKET_INDEX):
        return
    client.indices.create(
        index=TICKET_INDEX,
        body={
            "settings": {"index.knn": True},
            "mappings": {
                "properties": {
                    "ticket_id": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "severity": {"type": "keyword"},
                    "site_code": {"type": "keyword"},
                    "device_id": {"type": "keyword"},
                    "title": {"type": "text"},
                    "description": {"type": "text"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": EMBEDDING_DIM,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "lucene",
                            "parameters": {"ef_construction": 128, "m": 16},
                        },
                    },
                }
            },
        },
    )


def main() -> None:
    client = OpenSearch(hosts=[OPENSEARCH_URL], http_compress=True, timeout=60)
    ensure_index(client)

    with psycopg.connect(PG_DSN) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT ticket_id, category, severity, site_code, device_id, title, description
               FROM tickets ORDER BY ticket_id"""
        )
        rows = cur.fetchall()

    print(f"Embedding {len(rows)} tickets...")
    batch = 32
    actions = []
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        vectors = embed_many([f"{title}\n\n{desc}" for *_, title, desc in chunk])
        for (ticket_id, category, severity, site_code, device_id, title, desc), vec in zip(
            chunk, vectors
        ):
            actions.append(
                {
                    "_index": TICKET_INDEX,
                    "_id": ticket_id,
                    "_source": {
                        "ticket_id": ticket_id,
                        "category": category,
                        "severity": severity,
                        "site_code": site_code,
                        "device_id": device_id,
                        "title": title,
                        "description": desc,
                        "embedding": vec,
                    },
                }
            )

    helpers.bulk(client, actions)
    client.indices.refresh(index=TICKET_INDEX)
    print(f"Indexed {len(actions)} tickets into '{TICKET_INDEX}'")

    # ---------- ค้นหาด้วย kNN ----------
    query_text = "ลูกค้าแจ้งเน็ตหลุดเป็นช่วง ๆ ที่ไซต์ NBI"
    query_vector = embed_many([query_text])[0]

    result = client.search(
        index=TICKET_INDEX,
        body={
            "size": 5,
            "query": {"knn": {"embedding": {"vector": query_vector, "k": 5}}},
        },
    )
    print(f"\nคำค้น: {query_text}\n")
    for hit in result["hits"]["hits"]:
        src = hit["_source"]
        print(f"  {hit['_score']:.3f}  {src['ticket_id']}  [{src['category']}]  {src['title']}")


if __name__ == "__main__":
    main()
```

รันด้วย:

```bash
uv run python ticket_opensearch_lab.py
```

### ผลลัพธ์ที่ควรเห็น

```
Embedding 117 tickets...
Indexed 117 tickets into 'tickets-lab'

คำค้น: ลูกค้าแจ้งเน็ตหลุดเป็นช่วง ๆ ที่ไซต์ NBI

  0.853  TK-25-00001  [intermittent]  อินเทอร์เน็ตหลุดเป็นช่วงๆ ตั้งแต่เมื่อวาน
  0.819  TK-25-00005  [intermittent]  เน็ตหลุดซ้ำ เคสเดิมที่เคยแจ้งไว้
  0.814  TK-25-00002  [intermittent]  เน็ตกระตุกเป็นช่วง ใช้งานไม่ต่อเนื่อง
  0.792  TK-25-00004  [intermittent]  หลุดบ่อยช่วงบ่าย
  0.747  TK-25-00102  [slow]  latency สูงผิดปกติช่วงเย็น
```

(จำนวน ticket จริงในระบบอาจต่างจาก 117 เล็กน้อยขึ้นกับชุดข้อมูลที่ seed ไว้ แต่รูปแบบผลลัพธ์ควรเหมือนกัน)

**วิธีอ่านผลลัพธ์นี้**:

- **`Indexed N tickets`** ต้องมีค่าเท่ากับ `SELECT count(*) FROM tickets` เป๊ะ — ถ้าน้อยกว่านั้นแปลว่ามีแถวที่ embed ไม่สำเร็จระหว่างทาง (เช่น ไม่มี network provider คืนค่ามาให้ครบทุก batch)
- **คะแนนหน้าแต่ละบรรทัด** (0.853, 0.819, ...) คือ cosine similarity ระหว่าง query กับ ticket — ยิ่งใกล้ 1 ยิ่งใกล้เคียงเชิงความหมาย ไม่ใช่คะแนนความถูกต้อง
- **สังเกตว่า 4 ใน 5 ผลลัพธ์เป็นหมวด `intermittent`** ทั้งที่คำค้นไม่มีคำว่า "intermittent" อยู่เลย และแต่ละ ticket ก็ใช้คำบรรยายอาการคนละคำกัน ("หลุดเป็นช่วงๆ", "หลุดซ้ำ", "กระตุกเป็นช่วง", "หลุดบ่อยช่วงบ่าย") — นี่คือหลักฐานว่าโมเดล embedding จับ **ความหมายร่วม** ของอาการได้ ไม่ใช่แค่จับคำที่ตรงกัน
- **ผลลัพธ์อันดับ 5 เป็นหมวด `slow` คะแนนต่ำสุด (0.747)** — ยังพอเกี่ยวข้องกัน (ปัญหาเครือข่ายเหมือนกัน) แต่ห่างจากอาการ "หลุดเป็นช่วงๆ" มากกว่า 4 อันดับแรก คะแนนที่ลดหลั่นกันแบบนี้คือสัญญาณว่า ranking ทำงานถูกต้อง ไม่ใช่ทุกผลลัพธ์เกี่ยวข้องเท่ากันหมด

### ทดลองต่อ

1. เปลี่ยน `query_text` เป็นประโยคที่ไม่มีคำร่วมกับ ticket ใด ๆ ตรง ๆ เลย (เช่นบรรยายอาการแทนคำเทคนิค) แล้วสังเกตว่ายังหา ticket ที่เกี่ยวข้องเจอหรือไม่
2. ลองค้นหาด้วย `match` query ธรรมดา (keyword) เทียบกับ `knn` query ด้วยคำค้นเดียวกัน แล้วเทียบผลลัพธ์ — นี่คือหลักฐานที่ใช้ตอบคำถาม "ทำไมต้อง semantic search"

### เกณฑ์ผ่าน

- [ ] สร้าง index `tickets-lab` สำเร็จ โดย field `embedding` มี `dimension` ตรงกับ `EMBEDDING_DIM` ใน `.env`
- [ ] index ticket ได้ครบตามจำนวนแถวในตาราง `tickets` (`count` ของ index ตรงกับ `SELECT count(*) FROM tickets`)
- [ ] คำค้นภาษาธรรมชาติ (ไม่ใช่คำที่ตรงกับ title เป๊ะ) คืนผลลัพธ์ที่เกี่ยวข้องอย่างน้อย 3 ใบ พร้อมคะแนน similarity เรียงจากมากไปน้อย
- [ ] อธิบายได้ว่าทำไมผลลัพธ์จาก `knn` query กับ `match` query ต่างกัน โดยใช้ตัวอย่างจริงจากการทดลองข้อ 2

### สิ่งที่ต้องส่ง

- ไฟล์ `ticket_opensearch_lab.py`
- ผลลัพธ์การค้นหา (คัดลอกจาก terminal) อย่างน้อยหนึ่งคำค้นที่แสดงให้เห็นว่า semantic search เจอสิ่งที่ keyword search พลาด

---

## ต่อไป

→ [Module 3: เรียก API และให้ตอบเป็น JSON](03-module3-json-api.md)
