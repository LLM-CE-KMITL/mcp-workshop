# Lab เสริม · Ingestion Pipeline — เอกสาร → Markdown → Vector

**12:30 – 13:00** (30 นาที) · ต่อจาก Module 2

> ตรงกับหัวข้อติดตามผลครั้งที่ 1 (30 วัน) ใน [reference/production-mapping.md](../reference/production-mapping.md): *"แปลงเอกสารเป็น Markdown + embed"*

---

## เป้าหมาย

สร้าง pipeline ที่เอกสารจริงขององค์กรต้องผ่านก่อนจะค้นหาด้วยความหมายได้ — เหมือนที่ระบบต้องทำจริงตอนขึ้น production ต่อยอดจาก Module 2 แต่เปลี่ยนเป้าหมายจาก ticket แถวเดียวเป็นเอกสารยาวที่ต้องตัดเป็นชิ้นย่อยก่อน

```mermaid
flowchart LR
    A["เอกสารต้นทาง<br/>Word / PDF / config"] --> B["แปลงเป็น Markdown"]
    B --> C["Chunk ตามหัวข้อ ##"]
    C --> D["นับ token<br/>ตรวจขนาด"]
    D --> E["Embed"]
    E --> F[("OpenSearch<br/>network-docs")]
```

---

## เหตุผลที่ต้องใช้ Markdown

| รูปแบบ | ปัญหา |
|---|---|
| PDF | โครงสร้างหาย ตารางเพี้ยน ลำดับข้อความสลับ |
| Word | มี metadata ปนอยู่มาก แปลงยาก |
| **Markdown** | **มีหัวข้อชัดเจน จึงสามารถ chunk ตามความหมายได้** · ทำ diff ได้ · อ่านได้ทั้งคนและเครื่อง |

หัวข้อ (`##`) คือขอบเขตความหมายตามธรรมชาติ ทำให้ chunk แล้วขั้นตอนกับคำอธิบายไม่ถูกตัดขาดจากกัน — หลักการเดียวกับที่ Module 2 ใช้ตอน chunk ticket แต่คราวนี้ไม่มี ticket แถวเดียวให้ embed ตรงๆ ต้องตัดเอกสารยาวเป็นชิ้นย่อยก่อน

---

## 1. ดู pipeline ที่มีอยู่

ระบบนี้มีฟังก์ชัน chunk อยู่แล้วสองจุด — [`docker/seeder/seed_opensearch.py`](../../docker/seeder/seed_opensearch.py) ที่ seed ข้อมูลตั้งต้น:

```python
def _chunk_markdown(text: str, max_chars: int = 900) -> list[str]:
    # แบ่งตามหัวข้อ ## ก่อน แล้วค่อยแบ่งตามความยาว (นับ "ตัวอักษร")
```

**หลักการที่ใช้ร่วมกัน**: การ chunk ตามหัวข้อมีความสำคัญมากกว่าเทคนิค overlap ที่ซับซ้อน หากขั้นตอนการแก้ปัญหาถูกตัดขาดออกจากกัน ไม่ว่า overlap จะออกแบบมาดีเพียงใดก็จะค้นหาผลลัพธ์ได้ไม่ครบถ้วน

**แต่การนับด้วยตัวอักษรมีปัญหา** — เชื่อมกับ Module 1 โดยตรง: chunk ที่ยาว 900 ตัวอักษรเท่ากัน จะได้ token ต่างกันมากระหว่างไทยกับอังกฤษ การ chunk ด้วยจำนวนตัวอักษรจึงให้ผลไม่สม่ำเสมอ — **ควร chunk ด้วยจำนวน token** นี่คือสิ่งที่ [`scripts/ingest_docs.py`](../../scripts/ingest_docs.py) ทำผ่าน `_chunk_markdown_by_tokens()` ซึ่งเป็น pipeline ที่ lab นี้จะใช้ต่อ

---

## 2. สิ่งที่ต้องทำ

### 2.1 เพิ่มเอกสารของตัวเอง

```bash
cat > "data/mock_fs/runbooks/my-runbook-$(whoami).md" <<'EOF'
# ขั้นตอนตรวจสอบเมื่อ BGP session หลุด

## อาการที่ควรสงสัย
BGP neighbor state เปลี่ยนเป็น Idle หรือ Active ค้างนานผิดปกติ

## ขั้นตอน
1. ตรวจ `show bgp neighbor` ดูค่า last error
2. ตรวจว่า TCP session (port 179) เชื่อมต่อได้หรือไม่
3. ถ้า neighbor อยู่คนละ AS ตรวจ policy ที่กรอง route ก่อนเสมอ
EOF
```

(ตั้งชื่อไฟล์ให้ไม่ซ้ำกับเพื่อนร่วมห้องด้วย `$(whoami)` เพราะทุกคนใช้ index `network-docs` ร่วมกัน)

### 2.2 เขียนสคริปต์ ingest

```python
# 1. อ่านไฟล์ .md ทั้งหมดใน data/mock_fs/runbooks/
# 2. chunk ด้วย _chunk_markdown_by_tokens (นับ token ไม่ใช่ตัวอักษร)
# 3. นับ token ของแต่ละ chunk ด้วย agent/tokenizer.py
# 4. เตือนถ้า chunk ไหนเกิน 512 token
# 5. embed แล้ว index เข้า network-docs
```

### 2.3 ตรวจสอบขนาด chunk — ขั้นตอนที่มักถูกมองข้าม

```python
from agent import tokenizer

MAX_TOKENS_PER_CHUNK = 512

# ใช้ enumerate เพื่อให้รู้ว่ากำลังเช็ค Chunk ลำดับที่เท่าไหร่
for idx, chunk in enumerate(chunks):

    # นับจำนวน token ของ chunk ปัจจุบัน
    n_tokens = tokenizer.count(chunk)

    # ตรวจสอบเงื่อนไขว่าเกิน 512 หรือไม่
    if n_tokens > MAX_TOKENS_PER_CHUNK:
        print(f"  ⚠️ WARNING: Chunk #{idx} ยาว {n_tokens} tokens (เกินเกณฑ์ {MAX_TOKENS_PER_CHUNK})")
    else:
        print(f"  ✅ Chunk #{idx}: {n_tokens} tokens (ผ่านเกณฑ์)")
```

### 2.4 ทดสอบว่าค้นเจอ

ถาม Chainlit หรือ MCP Inspector: *"ถ้า BGP หลุดควรตรวจอะไรก่อน"* — ต้องเจอ runbook ที่เพิ่งเพิ่มเข้าไป

---

## เฉลย

[`scripts/ingest_docs.py`](../../scripts/ingest_docs.py) ทำสิ่งข้างต้นครบทุกข้อไว้แล้ว เป็น pipeline ที่ทำงานได้จริง ใช้ตัว embed เดียวกับ Module 2 — โค้ดส่วนที่ต่างจากขั้นที่ 1:

```python
def _chunk_markdown_by_tokens(text: str, max_tokens: int = 400) -> list[str]:
    """แบ่ง chunk ตามหัวข้อ (##) ก่อน แล้วถ้าหัวข้อใดยาวเกิน max_tokens
    ให้ซอยย่อยด้วยการนับ token จริง เพื่อความสม่ำเสมอของขนาด chunk"""
    sections = text.split("\n## ")
    ...
```

รันด้วย:

```bash
uv run python scripts/ingest_docs.py
```

**ผลลัพธ์ที่ควรเห็น** (รันจริงตอนเตรียมเอกสารนี้ กับเอกสารตัวอย่าง 4 ไฟล์ที่มีอยู่แล้ว):

```
=== เริ่มกระบวนการ Ingest เอกสารเข้า network-docs ===

📄 กำลังประมวลผลไฟล์: escalation-matrix.md
  ✅ Chunk #0: 203 tokens
  ✅ Chunk #1: 111 tokens

📄 กำลังประมวลผลไฟล์: change-window-policy.md
  ✅ Chunk #0: 16 tokens
  ✅ Chunk #1: 74 tokens
  ✅ Chunk #2: 63 tokens
  ✅ Chunk #3: 147 tokens

📄 กำลังประมวลผลไฟล์: my-runbook.md
  ✅ Chunk #0: 9 tokens
  ✅ Chunk #1: 25 tokens
  ✅ Chunk #2: 61 tokens

📄 กำลังประมวลผลไฟล์: mtu-standard.md
  ✅ Chunk #0: 94 tokens
  ✅ Chunk #1: 37 tokens
  ✅ Chunk #2: 178 tokens

========================================
🎉 Ingest สำเร็จทั้งหมด 12 Chunks
⚠️ พบบันทึกเตือน Chunk ยาวเกินเกณฑ์: 0 ชิ้น
========================================
```

ไฟล์ของตัวเองที่เพิ่งเพิ่มจะปรากฏเป็นอีกหนึ่งบล็อก `📄` ในผลลัพธ์จริงของแต่ละคน จำนวน chunk รวมจึงมากกว่า 12

ตรวจสอบง่ายๆ ก่อนใน OpenSearch Dev Tools ว่าเอกสารเข้า index จริง:

```
GET network-docs/_search
{"size": 10, "query": {"match_all": {}}}
```

จากนั้นค้นด้วยคำถามภาษาธรรมชาติจริงผ่าน kNN (แบบเดียวกับ Module 2):

```bash
uv run python -c "
import os, httpx
from dotenv import load_dotenv
load_dotenv('.env')
from opensearchpy import OpenSearch

EMB = os.getenv('EMBEDDING_BASE_URL', 'https://openrouter.ai/api/v1').rstrip('/') + '/embeddings'
r = httpx.post(EMB, json={'model': os.getenv('EMBEDDING_MODEL','baai/bge-m3'),
                           'input': ['BGP หลุดควรตรวจอะไรก่อน']},
               headers={'Authorization': f\"Bearer {os.getenv('LLM_API_KEY','not-needed')}\"}, timeout=60)
vec = r.json()['data'][0]['embedding']

client = OpenSearch(hosts=[os.getenv('OPENSEARCH_URL', 'http://admin:admin_dev_password@localhost:9200')])
res = client.search(index='network-docs', body={'size': 3, 'query': {'knn': {'embedding': {'vector': vec, 'k': 3}}}})
for hit in res['hits']['hits']:
    print(hit['_score'], hit['_source'].get('title'))
"
```

**ผลลัพธ์ที่ควรเห็น** (ทดสอบด้วยคำค้นที่ใกล้เคียงเรื่อง `interface flap`):

```
0.8542195 ขั้นตอนตรวจสอบ optical power
0.80352074 การวินิจฉัยปัญหาเน็ตหลุดเป็นช่วง (intermittent drop)
0.7801685 ขั้นตอนตรวจสอบ optical power
```

เอกสารของตัวเองควรขึ้นเป็นอันดับต้นๆ ถ้าคำค้นตรงกับหัวข้อที่เขียนไว้ — ถ้าไม่เจอเลย ให้ตรวจว่า ingestion รอบล่าสุดรันผ่านจริงและไม่มี error

---

## เกณฑ์ผ่าน

- [ ] เอกสารใหม่ถูก index เข้า `network-docs`
- [ ] แต่ละ chunk มี `token_count` ที่นับด้วย tokenizer ไม่ใช่ตัวอักษร (เชื่อมกับ Module 1)
- [ ] ไม่มี chunk ไหนที่ตัดขั้นตอนขาดครึ่ง (ลองเปิดดู field `content` ของแต่ละ chunk ใน OpenSearch Dev Tools)
- [ ] ค้นเจอด้วยคำถามภาษาธรรมชาติ (ไม่ใช่คำที่ตรงกับหัวข้อเป๊ะ)
- [ ] มีรายงานว่า chunk ยาวเกินเกณฑ์กี่ชิ้น

---

## โบนัส (ถ้าเวลาเหลือ)

1. **ลองไฟล์ที่ไม่มีหัวข้อ `##` เลย** (เขียนเป็นย่อหน้ายาวๆ) แล้วดูว่า `_chunk_markdown_by_tokens` จัดการอย่างไร
2. **ตรวจของซ้ำ** — รัน `scripts/ingest_docs.py` ซ้ำสองรอบติดกัน แล้วดูว่าจำนวน chunk ใน index เพิ่มขึ้นเป็นสองเท่าหรือไม่ (คำใบ้: `chunk_id` คำนวณจาก hash ของ `file_name + idx + เนื้อหา` — ค่าเดิมจึงได้ id เดิม)
3. **รองรับ PDF** — ใช้ `pypdf` แปลงเป็น Markdown ก่อน แล้วเปรียบเทียบว่าโครงสร้างสูญหายไปมากน้อยเพียงใดเทียบกับไฟล์ Markdown ตรงๆ

---

## สำหรับ Production

| ประเด็น | ในห้อง | ของจริง |
|---|---|---|
| ปริมาณ | ไม่กี่ runbook | เอกสารโครงข่ายทั้งองค์กร |
| แหล่ง | ไฟล์ในเครื่อง (`data/mock_fs/`) | SharePoint / Confluence / ระบบเอกสารภายใน |
| ความถี่ | ครั้งเดียว | ต้องมี incremental ingestion |
| เวอร์ชัน | ไม่มี | ต้องรู้ว่า chunk มาจากเอกสารเวอร์ชันไหน |

---

## ต่อไป

→ [Module 3: เรียก API และให้ตอบเป็น JSON](05-module3-json-api.md)
