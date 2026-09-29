# Lab เสริม · Ingestion Pipeline — เอกสาร → Markdown → Vector

**12:30 – 13:00** (30 นาที) · เป้าหมาย: เห็น pipeline ที่เอกสารจริงขององค์กรต้องผ่านก่อนถึงจะค้นหาด้วยความหมายได้ — ต่อยอดจาก Module 2 แต่เปลี่ยนเป้าหมายจาก ticket เป็นเอกสาร

---

## ทำไมต้อง Markdown

| รูปแบบ | ปัญหา |
|---|---|
| PDF | โครงสร้างหาย ตารางเพี้ยน ลำดับข้อความสลับ |
| Word | มี metadata ปนเยอะ แปลงยาก |
| **Markdown** | **มีหัวข้อชัดเจน → chunk ตามความหมายได้** · diff ได้ · อ่านออกทั้งคนและเครื่อง |

หัวข้อ (`##`) คือขอบเขตความหมายตามธรรมชาติ ทำให้ chunk แล้วขั้นตอนกับคำอธิบายไม่ถูกตัดขาดจากกัน — หลักการเดียวกับที่ Module 2 ใช้ตอน chunk ticket แต่คราวนี้ไม่มี ticket แถวเดียวให้ embed ตรงๆ ต้องตัดเอกสารยาวเป็นชิ้นย่อยก่อน

```mermaid
flowchart LR
    A["เอกสารต้นทาง<br/>Word / PDF / config"] --> B["แปลงเป็น Markdown"]
    B --> C["Chunk ตามหัวข้อ ##"]
    C --> D["นับ token<br/>ตรวจขนาด"]
    D --> E["Embed"]
    E --> F[("OpenSearch<br/>network-docs")]
```

---

## โค้ดจริงที่ทำหน้าที่นี้อยู่แล้ว

[`scripts/ingest_docs.py`](../../scripts/ingest_docs.py) คือ pipeline ที่ทำงานได้จริง ใช้ตัว embed เดียวกับ Module 2 และ Lab ก่อนหน้า:

```python
def _chunk_markdown_by_tokens(text: str, max_tokens: int = 400) -> list[str]:
    """แบ่ง chunk ตามหัวข้อ (##) ก่อน แล้วถ้าหัวข้อใดยาวเกิน max_tokens
    ให้ซอยย่อยด้วยการนับ token จริง เพื่อความสม่ำเสมอของขนาด chunk"""
    sections = text.split("\n## ")
    ...
```

**หลักการ**: chunk ตามหัวข้อสำคัญกว่าเทคนิค overlap ที่ซับซ้อน — ถ้าขั้นตอนการแก้ปัญหาถูกตัดครึ่งกลางหัวข้อ ต่อให้ overlap ดีแค่ไหนก็ค้นเจอไม่ครบ และ**ตัดด้วยจำนวน token ไม่ใช่จำนวนตัวอักษร** เชื่อมกับ Module 1 โดยตรง: chunk ที่ยาว 900 ตัวอักษรเท่ากัน จะได้ token ต่างกันมากระหว่างไทยกับอังกฤษ

---

## สิ่งที่ต้องทำ

### 1. เพิ่มเอกสารของตัวเอง

```bash
cat > data/mock_fs/runbooks/my-runbook-$(whoami).md <<'EOF'
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

### 2. รัน ingestion จริง

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

### 3. ทดสอบว่าค้นเจอ

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

## สิ่งที่ต้องสังเกต

- [ ] เอกสารใหม่ถูก index เข้า `network-docs` และค้นเจอด้วยคำถามภาษาธรรมชาติ (ไม่ใช่คำที่ตรงกับหัวข้อเป๊ะ)
- [ ] แต่ละ chunk มี `token_count` ที่นับด้วย tokenizer ของ Qwen ไม่ใช่ตัวอักษร (เชื่อมกับ Module 1)
- [ ] ไม่มี chunk ไหนที่ตัดขั้นตอนขาดครึ่ง (ลองเปิดดู field `content` ของแต่ละ chunk ใน OpenSearch Dev Tools)
- [ ] เข้าใจได้ว่าทำไม chunk ตามหัวข้อ `##` ถึงปลอดภัยกว่าการตัดตามจำนวนตัวอักษรตายตัว

---

## โบนัส (ถ้าเวลาเหลือ)

1. **ลองไฟล์ที่ไม่มีหัวข้อ `##` เลย** (เขียนเป็นย่อหน้ายาวๆ) แล้วดูว่า `_chunk_markdown_by_tokens` จัดการอย่างไร
2. **ตรวจของซ้ำ** — รัน `scripts/ingest_docs.py` ซ้ำสองรอบติดกัน แล้วดูว่าจำนวน chunk ใน index เพิ่มขึ้นเป็นสองเท่าหรือไม่ (คำใบ้: `chunk_id` คำนวณจาก hash ของเนื้อหา)

---

## ต่อไป

→ [Module 3: เรียก API และให้ตอบเป็น JSON](05-module3-json-api.md)
