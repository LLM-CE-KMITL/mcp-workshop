# Full Demo — ลองระบบให้จบภายใน 10 นาที ก่อนเริ่มเรียนจริง

หน้านี้ไม่ใช่บทเรียน — เป็น**ทางลัดให้เห็นของจริงก่อน** ว่าตลอด 3 วันจะสร้างอะไรขึ้นมา
รันตามนี้ครั้งเดียวจบ แล้วค่อยย้อนกลับไปเริ่ม [03-prerequisites.md](03-prerequisites.md) ตามลำดับปกติ

---

## 1. ภาพรวมสถาปัตยกรรม

ระบบที่จะได้ลองคือ **AI Agent ที่คุยกับเครือข่าย IP-MPLS ผ่านภาษาธรรมชาติ** โดยมี MCP Server เป็นตัวกลางเข้าถึง 3 ฐานข้อมูล:

```mermaid
flowchart TB
    UI["Chainlit UI<br/>:8000 dev / :8100 demo"]
    API["Agent API (FastAPI)<br/>:8080 dev / :8180 demo<br/>Intent -> Memory -> ReAct Loop -> Synthesizer -> Grounding"]
    MCP["MCP Server<br/>Tools / Resources<br/>:9000"]
    LLM["OpenRouter<br/>LLM + Embedding"]
    PG[("PostgreSQL + pgvector<br/>tickets, circuits, customers")]
    NEO[("Neo4j<br/>topology, devices, adjacency")]
    OS[("OpenSearch<br/>logs, doc chunks + vectors")]

    UI <-->|SSE stream| API
    API <-->|chat / embedding calls| LLM
    API <-->|MCP protocol| MCP
    MCP --> PG
    MCP --> NEO
    MCP --> OS
```

**Agent API** ประมวลผลคำถามผ่าน 5 ขั้นตอนเรียงกัน: Intent Gate → Memory → ReAct Loop (+ Loop Guard) → Synthesizer → Grounding
รายละเอียดแต่ละขั้นตอน + เหตุผลเชิงสถาปัตยกรรม อยู่ที่ [01-architecture.md](01-architecture.md)

---

## 2. ตั้งค่า `.env`

```bash
cp .env.example .env
```

เปิด `.env` แล้วแก้อย่างน้อย 1 บรรทัด — ใส่ API key ของ OpenRouter (สมัครฟรีที่ https://openrouter.ai/keys) ใน**ส่วน LLM**:

```dotenv
# ---------- LLM (OpenAI-compatible endpoint) ----------
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_MODEL=qwen/qwen3-30b-a3b
```
ต้องแก้แค่ `LLM_API_KEY` บรรทัดเดียว ที่เหลือปล่อยเป็นค่า default

ใน**ส่วน Embedding** ปล่อยเป็นค่า default ได้เลย ไม่ต้องแก้อะไร (ใช้ API key เดียวกันกับ LLM เพราะเรียกผ่าน OpenRouter เหมือนกัน):

```dotenv
# ---------- Embedding ----------
EMBEDDING_BASE_URL=https://openrouter.ai/api/v1
EMBEDDING_MODEL=baai/bge-m3
EMBEDDING_DIM=1024
```

ค่าชุดนี้ (LLM + Embedding) ผ่านการทดสอบ end-to-end มาแล้วว่าทำงานร่วมกันได้ครบทั้ง 3 ฐานข้อมูล

> **อย่าเปลี่ยน `EMBEDDING_DIM` ตามใจ** ถ้าเปลี่ยน `EMBEDDING_MODEL` เป็นตัวอื่น ต้องเช็คว่า dimension ของมันไม่เกิน 2000 (ข้อจำกัดของ pgvector HNSW index) ไม่งั้น PostgreSQL จะ init ไม่ผ่านทั้งระบบ

---

## 3. รันทั้งระบบ — คำสั่งเดียว

```bash
docker compose -f docker/docker-compose.yml --env-file .env up -d postgres pgadmin neo4j opensearch opensearch-dashboards mailhog && docker compose -f docker/docker-compose.yml --env-file .env build seeder && docker compose -f docker/docker-compose.yml --env-file .env up seeder && docker compose -f docker/docker-compose.yml --env-file .env --profile demo up -d mcp-demo
```

`&&` การันตีว่าถ้าขั้นไหน fail (เช่น seed ไม่ผ่าน) จะหยุดทันที ไม่ไปขั้นถัดไปแบบพัง ๆ

รอจนเห็นบรรทัดสุดท้ายจบ (การ build + seed ครั้งแรกใช้เวลาราว 3-5 นาที ขึ้นกับเครื่องและความเร็วเน็ต)

---

## 4. เข้าใช้งาน

เปิด Chatbot UI ที่:

**http://localhost:8100**

---

## 5. ตัวอย่างคำถามที่ลองได้ (5 แบบ)

พิมพ์ในช่องแชทที่ **http://localhost:8100**

### 1) คำถามแหล่งเดียว — เร็ว ใช้ token น้อย
```
ticket ที่ยังไม่ปิดตอนนี้มีอะไรบ้าง เรียงตามความรุนแรง
```
สังเกต: เรียก tool ตัวเดียว (`search_tickets`) ไม่ต้องคิดวางแผนซับซ้อน

### 2) คำถามข้าม 3 ระบบ — ไฮไลต์ของเดโม
```
ทำไมช่วงสองสัปดาห์นี้ถึงมีลูกค้าแจ้งเน็ตหลุดซ้ำๆ หลายราย
```
สังเกต: agent หา ticket ก่อน (Postgres) → เอาอุปกรณ์ไปหาจุดร่วมใน topology (Neo4j) → เช็ค log ของอุปกรณ์นั้น (OpenSearch) — คำถามไม่ได้บอกพื้นที่/อุปกรณ์เลยสักคำ

### 3) ค้นหาแบบความหมาย (semantic search)
```
มีเอกสารหรือ runbook ที่พูดถึงการแก้ปัญหา SFP หรือ transceiver ไหม
```
สังเกต: ใช้ `search_docs_semantic` ค้นด้วยเวกเตอร์ใน OpenSearch ไม่ใช่ keyword ตรงตัว

### 4) คำถามนอกขอบเขต — ทดสอบ Intent Gate
```
ช่วยเขียนอีเมลลาพักร้อนให้หน่อย
```
สังเกต: **0 tool call** ปฏิเสธตั้งแต่ต้นทาง ไม่แตะฐานข้อมูลเลยแม้แต่แถวเดียว

### 5) ทดสอบความจำ + การเปลี่ยนหัวข้อ
ต้องมี "ข้อสรุป" ที่มีความหมายให้จำก่อน ไม่ใช่แค่รายชื่ออุปกรณ์ — ใช้บทสนทนา 3 ขั้นตอนนี้ (ตรงกับ turn 9 ของ [day2/08-challenge4-topic-shift-survival.md](../day2/08-challenge4-topic-shift-survival.md)):

```
ทำไมช่วงสองสัปดาห์นี้ถึงมีลูกค้าแจ้งเน็ตหลุดซ้ำๆ หลายรายที่ฝั่งนนทบุรี
```
รอให้ตอบจบ (ควรได้ข้อสรุปว่า `APE-NBI-03` มี interface flapping) แล้วเปลี่ยนหัวข้อ
```
เปลี่ยนเรื่อง ขอดูฝั่งกรุงเทพ
```
```
อุปกรณ์ฝั่งกรุงเทพมีอะไรบ้าง
```
แล้วถามย้อนกลับ
```
เมื่อกี้เรื่องนนทบุรีสรุปว่าอะไร
```
สังเกต:
- หลังคำสั่ง "เปลี่ยนเรื่อง" — `context_tokens` ลดลงชัดเจน (ดูได้จาก event `topic_changed`) เพราะบทสนทนาเรื่องนนทบุรีถูกสรุปเหลือบรรทัดเดียวแทนที่จะเก็บทั้งหมด
- คำถามสุดท้าย คำตอบควรมีคำว่า **`APE-NBI-03`** อยู่ (มาจากสรุปที่เก็บไว้ ไม่ใช่ข้อมูลใหม่)
- เกณฑ์ของ Challenge 4 คือ **เรียก tool ไม่เกิน 1 ครั้ง** ในคำถามนี้ (ไม่จำเป็นต้องเป็น 0 — ถ้า agent เรียก tool ยืนยันซ้ำ 1 ครั้งก่อนตอบ ก็ยังถือว่าผ่าน)
- ถ้าเรียก tool มากกว่า 1 ครั้ง หรือคำตอบไม่มี `APE-NBI-03` เลย — นั่นคือสิ่งที่ [day2/08-challenge4-topic-shift-survival.md](../day2/08-challenge4-topic-shift-survival.md) ให้ผู้เรียนไปแก้เอง (ดู hint ในโจทย์ เรื่องปรับ prompt ของ `_summarise_topic` ใน [memory.py](../../apps/agent-api/agent/memory.py))

---

## 6. ล้างทั้งหมดเพื่อเริ่มใหม่

```bash
docker compose -f docker/docker-compose.yml --env-file .env --profile demo down && docker compose -f docker/docker-compose.yml --env-file .env down -v
```

คำสั่งนี้ปิด container ทั้งหมด **และลบ volume ข้อมูลทิ้งทั้งหมด** (postgres, neo4j, opensearch, pgadmin) — กลับสู่สภาพเปล่าเหมือนยังไม่เคยรันมาก่อน ต้องเริ่มใหม่ตั้งแต่ขั้นตอนที่ 3 ถ้าจะลองอีกครั้ง

---

## ถัดไป

เริ่มหลักสูตรจริงที่ [03-prerequisites.md](03-prerequisites.md)
