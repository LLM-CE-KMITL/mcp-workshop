# เฉลยวันที่ 1

> ⚠️ อ่านก่อนลอง = เสียโอกาสเรียนรู้ · ดูวิธีใช้ที่ [../README.md](../README.md)

| ไฟล์ | เฉลยของ |
|---|---|
| `ticket_opensearch_lab.py` | [Module 2: Embeddings กับ OpenSearch](../../INSTRUCTIONS/day1/04-module2-embeddings-opensearch.md) |
| `workshop1_extractor.py` | [Workshop 1: ตัวแยกข้อมูล Ticket](../../INSTRUCTIONS/day1/07-workshop1-ticket-extractor.md) |

Module 1 และ Module 3 เป็นเนื้อหาบรรยาย/สาธิต ไม่มีไฟล์เฉลยแยก — Lab: Vector ใน PostgreSQL ([`02-lab-pg-vectors.md`](../../INSTRUCTIONS/day1/02-lab-pg-vectors.md)), Lab: Vector ใน Neo4j ([`03-lab-neo4j-vectors.md`](../../INSTRUCTIONS/day1/03-lab-neo4j-vectors.md)) และ Lab: Ingestion Pipeline เอกสาร Markdown ([`05-lab-ingestion-markdown.md`](../../INSTRUCTIONS/day1/05-lab-ingestion-markdown.md)) ก็ไม่มีไฟล์เฉลยแยกเช่นกัน เพราะทั้งสาม Lab อ้างอิงสคริปต์ที่ทำงานได้จริงอยู่แล้วที่ `scripts/embed_tickets.py`, `scripts/embed_devices.py` และ `scripts/ingest_docs.py`

---

## วิธีรัน

```bash
uv run solutions/day1/ticket_opensearch_lab.py
```

```bash
uv run solutions/day1/workshop1_extractor.py
```

**ต้องรันไฟล์แรกก่อนเสมอ** — `workshop1_extractor.py` ค้นหา ticket ที่คล้ายกันจาก index `tickets-lab` ที่ `ticket_opensearch_lab.py` เป็นผู้สร้าง ถ้ายังไม่มี index นี้ ขั้นตอนค้นหาจะคืนค่าว่างเปล่าโดยไม่ error

---

## 3 จุดที่ผู้เรียนพลาดมากที่สุดใน Module 2

| # | พลาดอะไร | อาการ |
|---|---|---|
| 1 | ไม่เรียง response ตาม `index` ก่อนจับคู่กับข้อความต้นทาง | **ไม่มี error ใดๆ** แต่ vector ไปผูกกับ ticket ผิดใบ ค้นแล้วได้ผลลัพธ์ที่ไม่ถูกต้อง — API ไม่รับประกันลำดับที่ส่งเข้าไป |
| 2 | กำหนด `dimension` ใน mapping ไม่ตรงกับ `EMBEDDING_DIM` จริง | `INSERT` ล้มเหลวทุกแถวตั้งแต่แถวแรก error ชี้ชัดแต่มักถูกมองข้ามเพราะดูเหมือนปัญหาที่ฐานข้อมูลไม่ใช่ปัญหาที่ mapping |
| 3 | embed แค่ `title` ไม่รวม `description` | ค้นพบผลลัพธ์ได้น้อยลงมาก เพราะรายละเอียดของอาการมักอยู่ใน `description` ไม่ใช่หัวเรื่อง |

จุดที่ 1 อันตรายที่สุด เนื่องจากระบบยังทำงานได้ปกติทุกอย่าง มีเพียงคำตอบที่ผิดพลาด — ยืนยันได้จริงจากการรัน: `SELECT count(*) FROM tickets` และ `GET tickets-lab/_count` ต้องได้ตัวเลขเท่ากันเป๊ะ (117 ในข้อมูลชุดปัจจุบัน) ถ้าเรียงผิดตัวเลขจะยังเท่ากันแต่เนื้อหาผูกผิดคู่โดยไม่มีสัญญาณเตือนใดๆ

---

## สิ่งที่ควรสังเกตใน Workshop 1

### `_repair_prompt()` คือหัวใจ

การ retry ซ้ำด้วย prompt เดิมมักได้ผลผิดแบบเดิม แต่การส่ง **ข้อความ error กลับไปให้โมเดลเห็น** ทำให้ครั้งที่สองกลายเป็นการแก้ไข ไม่ใช่การสุ่มใหม่

```python
{"role": "assistant", "content": raw},
{"role": "user", "content": f"ไม่ผ่านการตรวจสอบ\nข้อผิดพลาด: {error}\nส่ง JSON ที่แก้แล้วกลับมา"}
```

### Delimiter แยก "คำสั่ง" ออกจาก "ข้อมูล"

```python
{"role": "user", "content": f"<<<CONVERSATION\n{text}\n>>>CONVERSATION"}
```

เป็นการป้องกัน prompt injection ที่ได้ผลที่สุด และมีต้นทุนต่ำกว่าการพยายามกรอง keyword เพราะให้กรอบแก่โมเดลว่าสิ่งที่กำลังอ่านคือข้อมูล ไม่ใช่คำสั่ง

### `model_validator` ตรวจข้ามฟิลด์

`affected_device = "LPE-NBI-11"` คู่กับ `affected_site = "BKK"` เป็นสิ่งที่ **พิสูจน์ได้ว่าผิด** ไม่ใช่เพียงแค่ไม่น่าจะใช่ เพราะรหัสอุปกรณ์มีพื้นที่ระบุอยู่ในตัวเอง จึงควร reject แล้วให้แก้ไข

### Fallback ต้องไม่ throw

pipeline ที่หยุดทำงานเพราะแถวเดียวเสีย แย่กว่า pipeline ที่ติดธงแล้วทำต่อ

### ขั้นตอนใหม่: `find_similar_tickets()` เชื่อม Module 2 กับ Workshop 1 เข้าด้วยกัน

หลังสกัดข้อมูลสำเร็จ ฟังก์ชันนี้ embed ค่า `summary_th` ที่ได้ ด้วยรูปแบบเดียวกับ `ticket_opensearch_lab.py` แล้วค้นหาด้วย `knn` query กับ index `tickets-lab` — ผลจริงจากการทดสอบแสดงให้เห็นว่าค้นเจอ ticket ที่เกี่ยวข้องได้แม้คำอธิบายที่สกัดมาไม่มีศัพท์เทคนิคปนอยู่เลย (เช่น extraction พูดถึง "video conference หลุดบ่อย" แต่ยังจับคู่กับ ticket ประเภท `intermittent` อื่นๆ ได้ถูกต้องด้วยคะแนน similarity สูง) — นี่คือหลักฐานที่ตอบคำถามว่าทำไมต้องใช้ semantic search แทน keyword matching อย่างเดียว
