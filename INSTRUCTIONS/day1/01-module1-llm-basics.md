# Module 1 · LLM ทำงานอย่างไร

**09:00 – 10:15** (75 นาที) · เป้าหมาย: เข้าใจว่าโมเดลไม่ได้ "อ่าน" ข้อความแบบที่มนุษย์อ่าน แต่แปลงข้อความเป็นลำดับ token ก่อนเสมอ ต้นทุนของทุกคำขอจึงถูกวัดเป็นจำนวน token ไม่ใช่จำนวนตัวอักษรหรือจำนวนคำ และภาษาไทยมีต้นทุนที่แพงกว่าภาษาอังกฤษอย่างมีนัยสำคัญ

---

## 1. Token คืออะไร

โมเดลไม่เคยเห็น "ตัวอักษร" หรือ "คำ" โดยตรง ทุกข้อความที่ส่งเข้าไปจะถูก tokenizer ของโมเดลตัดเป็นหน่วยย่อยที่เรียกว่า token ก่อน แล้วแปลงเป็นตัวเลข (id) ให้โมเดลประมวลผล คำตอบที่โมเดลสร้างกลับมาก็เป็นลำดับ token id เช่นกัน ก่อนจะถูก decode กลับเป็นข้อความให้อ่านได้

```mermaid
flowchart LR
    T["ข้อความ<br/>(ไทย/อังกฤษปนกัน)"] --> TK["Tokenizer เฉพาะของโมเดล<br/>(BPE / SentencePiece)"]
    TK --> ID["ลำดับ token id"]
    ID --> M[["LLM"]]
    M --> ID2["ลำดับ token id ที่สร้างใหม่"]
    ID2 --> DEC["Decode กลับเป็นข้อความ"]
```

ประเด็นสำคัญที่มักเข้าใจผิด: **tokenizer เป็นของเฉพาะโมเดล ไม่ใช่ของภาษา** โมเดลแต่ละตระกูล (Qwen, GPT, Gemma, Llama) ฝึก tokenizer ของตัวเองจาก corpus ของตัวเอง คำเดียวกันจึงถูกตัดต่างกันไปตามโมเดลที่ใช้เสมอ

โปรเจกต์นี้ใช้ `qwen/qwen3-30b-a3b` เป็นโมเดลหลัก (ตั้งค่าใน `.env.example` ที่ `LLM_MODEL`) ดังนั้น token ที่ "จริง" สำหรับระบบนี้คือ token ที่ tokenizer ของ Qwen สร้างขึ้นเท่านั้น

---

## 2. กับดักที่พบบ่อยที่สุด: นับ token ผิดตัว

`tiktoken` เป็น tokenizer ของ OpenAI (ใช้ BPE แบบ `cl100k_base`) เป็นไลบรารีที่หาง่ายและมีคนใช้นับ token มากที่สุด แต่มันนับ token ของโมเดล GPT เท่านั้น การใช้มันนับ token ให้ Qwen จะได้ตัวเลขที่ผิด — และผิดไม่เท่ากันระหว่างข้อความภาษาไทยกับภาษาอังกฤษด้วย

โปรเจกต์นี้มีโมดูลที่สร้างไว้เพื่อพิสูจน์กับดักนี้โดยเฉพาะ: `apps/agent-api/agent/tokenizer.py`

```python
def count(text: str) -> int:
    """Best available token count for the model in use."""
    ...

def compare(text: str) -> dict:
    """Three-way comparison used by Module 1 and the token meter."""
    ...
```

`compare(text)` คืนค่าทั้งสามมุมมองของข้อความเดียวกัน:

| key | หมายถึง |
|---|---|
| `thai_words` | จำนวนคำที่ `pythainlp.word_tokenize` ตัดได้ — ใกล้เคียงกับที่คนอ่านออก |
| `model_tokens` | จำนวน token จริงที่ Qwen tokenizer เห็น (ค่าที่ถูกต้องสำหรับระบบนี้) |
| `tiktoken_tokens` | จำนวน token ถ้าใช้ tokenizer ของ OpenAI ผิดตัว |
| `tiktoken_error_pct` | ผิดไปกี่เปอร์เซ็นต์เทียบกับค่าจริง |
| `tokens_per_word` | token ต่อหนึ่งคำไทย — ยิ่งสูงยิ่งแพง |

ทดลองรันดูความต่างของสามค่านี้ก่อนเข้าห้อง lab:

```bash
uv run python - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path("apps/agent-api")))

from agent.tokenizer import compare

print(compare("ลิงก์ที่ไซต์ NBI หลุดเป็นช่วง ๆ ตั้งแต่เมื่อคืน ลูกค้าโทรมาแจ้งหลายรอบ"))
print(compare("The link at site NBI has been dropping intermittently since last night."))
PY
```

สังเกต `tiktoken_error_pct` ของสองประโยคนี้ — ประโยคภาษาไทยจะเบี่ยงเบนจากค่าจริงมากกว่าประโยคภาษาอังกฤษอย่างชัดเจน เพราะ `cl100k_base` ไม่เคยเห็นสัดส่วนอักขระไทยมากพอตอนฝึก จึงตัดเป็นชิ้นเล็กผิดธรรมชาติ (byte-level fallback) ในขณะที่ Qwen tokenizer ถูกฝึกด้วย corpus ที่มีภาษาไทยรวมอยู่ด้วย

### ผลลัพธ์ที่ควรเห็น

```
{'text_length': 70, 'model_tokens': 38, 'tiktoken_tokens': 68, 'thai_words': 20, 'tiktoken_error_pct': 78.9, 'tokens_per_word': 1.9}
{'text_length': 71, 'model_tokens': 15, 'tiktoken_tokens': 15, 'thai_words': 24, 'tiktoken_error_pct': 0.0, 'tokens_per_word': 0.62}
```

**วิธีอ่านผลลัพธ์นี้**:

- ประโยคที่ 1 (ไทย, ยาว 70 ตัวอักษร): Qwen เห็นจริง 38 token แต่ `tiktoken` นับได้ 68 token — **คลาดเคลื่อนไป 78.9%** เกือบสองเท่าตัว
- ประโยคที่ 2 (อังกฤษ, ยาว 71 ตัวอักษรใกล้เคียงกัน): Qwen กับ `tiktoken` นับได้ **เท่ากันเป๊ะ (15 token ทั้งคู่) คลาดเคลื่อน 0.0%** — เพราะคำภาษาอังกฤษทั่วไปมักถูกตัดเป็น token เดียวกันไม่ว่าจะใช้ tokenizer ของค่ายไหน
- ความยาวตัวอักษรใกล้เคียงกัน (70 vs 71) แต่ **Qwen เห็นประโยคไทยเป็น 38 token ในขณะที่ประโยคอังกฤษเห็นแค่ 15 token** — นี่คือหลักฐานตัวเลขจริงของ "ภาษาไทยแพงกว่า" ที่พูดถึงในหัวข้อ 3 ด้านล่าง ไม่ใช่แค่คำกล่าวอ้างลอยๆ
- ถ้าใช้ `tiktoken` ไปประมาณต้นทุนของข้อความไทยชุดนี้ จะเข้าใจผิดว่าแพงกว่าความเป็นจริงถึงเกือบสองเท่า — อันตรายเพราะทำให้ overestimate งบประมาณ ในขณะที่ประโยคอังกฤษจะประมาณได้ถูกต้องพอดี ทำให้ความคลาดเคลื่อนระหว่างสองภาษาไม่สม่ำเสมอกันเลย

> `agent/tokenizer.py` โหลด tokenizer จริงผ่าน `transformers.AutoTokenizer.from_pretrained(MODEL_ID)` โดย `MODEL_ID` มาจาก env var `TOKENIZER_MODEL_ID` (ค่าเริ่มต้นคือ `Qwen/Qwen3.5-35B-A3B`) หากโหลดไม่สำเร็จ (ไม่มีเน็ต/ยังไม่ได้ดาวน์โหลดน้ำหนักโมเดล) จะ fallback เป็นสูตรประมาณการที่ให้น้ำหนักอักขระไทยสูงกว่าอักขระอื่น (`thai / 1.6 + other / 4`) เพื่อให้ UI ยังทำงานได้แม้ออฟไลน์

> **แผนสำรอง (ไม่ต้องรันโค้ด)**: หากโหลด tokenizer จริงไม่สำเร็จและไม่ต้องการพึ่งสูตรประมาณการ ใช้ [The Tokenizer Playground](https://huggingface.co/spaces/Xenova/the-tokenizer-playground) แทนได้ — เว็บที่เลือก tokenizer ของโมเดลต่างๆ (รวม Qwen) แล้ววางข้อความเทียบจำนวน token ได้ทันทีโดยไม่ต้องติดตั้ง `transformers` หรือดาวน์โหลดน้ำหนักโมเดลลงเครื่อง เหมาะกับการตรวจสอบผลลัพธ์ของ Lab นี้อย่างรวดเร็วเช่นกัน

---

## 3. ทำไมภาษาไทยถึงแพงกว่า

สองเหตุผลหลักที่ทำให้ข้อความไทยใช้ token มากกว่าข้อความอังกฤษความยาวเทียบเท่ากัน:

1. **ภาษาไทยไม่มีช่องว่างระหว่างคำ** — tokenizer ต้องเดาขอบเขตคำเองจากรูปแบบอักขระ ทำให้มักตัดเป็นชิ้นเล็กกว่าคำจริง (sub-word) บ่อยกว่าภาษาที่มีช่องว่างคั่นคำอยู่แล้ว
2. **corpus ฝึก tokenizer ส่วนใหญ่เป็นภาษาอังกฤษ** — แม้ Qwen จะฝึกด้วยข้อมูลหลายภาษารวมไทย แต่สัดส่วนยังน้อยกว่าอังกฤษมาก คำไทยทั่วไปจึงมีโอกาสไม่ถูกรวมเป็น token เดียวเท่ากับคำอังกฤษทั่วไป

ผลลัพธ์เชิงปฏิบัติ: prompt ภาษาไทยความยาว "เท่ากัน" (นับเป็นตัวอักษรหรือนับเป็นคำ) กิน token มากกว่า และเสียค่าใช้จ่ายมากกว่า ประโยคเดียวกันเมื่อแปลเป็นอังกฤษ

### เรื่องต้นทุนเงินจริง

ระหว่างการอบรมนี้ `.env.example` ตั้งค่า `LLM_BASE_URL=https://openrouter.ai/api/v1` ไว้เป็นค่าเริ่มต้น — เรียกผ่าน OpenRouter ซึ่งคิดเงินจริงตามจำนวน token ทั้งขาเข้า (prompt) และขาออก (completion) การนับ token ผิดตัวจึงแปลว่าประมาณการต้นทุนผิดโดยตรง

เมื่อขึ้น production จริง (ดู `reference/local-llm-ollama-vllm.md`) แผนคือ self-host ด้วย vLLM เอง โครงสร้างต้นทุนจะเปลี่ยนจาก "จ่ายต่อ token" เป็น "ต้นทุน GPU ต่อเวลา" (`agent/llm.py` มีหมายเหตุนี้ไว้ในเอกสารประกอบของไฟล์) แต่จำนวน token ต่อคำขอยังคงเป็นตัวแปรสำคัญเหมือนเดิม เพราะกำหนดทั้ง latency และ throughput ต่อ GPU ที่มีอยู่จำกัด

---

## 4. Context Window: งบประมาณ token ที่มีจำกัดต่อหนึ่ง request

Context window คืองบ token รวมสูงสุดที่โมเดลรับได้ในหนึ่งคำขอ **(prompt ทั้งหมด + คำตอบที่จะสร้าง รวมกันต้องไม่เกินขีดจำกัดนี้)** ถ้า prompt ยาวเกินไป คำขอจะถูกปฏิเสธหรือถูกตัดท้าย และถ้า prompt ใกล้เต็ม context ที่เหลือไว้ให้โมเดลตอบก็จะน้อยลงตามไปด้วย

ในระบบจริงของโปรเจกต์นี้ ตัวเลขนี้ไม่ได้เป็นแค่ทฤษฎี — `apps/agent-api/main.py` มีการวัด `context_tokens` จริงของแต่ละ session ก่อนและหลังทุก turn (ฟิลด์ `context_tokens_before`/`context_tokens_after` ที่ส่งกลับให้ UI) และ `LLM_TIMEOUT_SECONDS` ใน `.env.example` กำหนดเวลาที่ยอมรอคำตอบก่อน timeout — prompt ที่ยาวมักใช้เวลานานขึ้นตามไปด้วย

**ถ้านับ token ผิดตั้งแต่ต้น การประมาณว่า context เหลือเท่าไรก็ผิดตามไปด้วย** — วันที่ 2 จะสร้าง agent ที่ต้องส่งประวัติ Thought/Action/Observation ทั้งหมด (scratchpad) กลับเข้าไปในทุกรอบของ ReAct loop ยิ่งวนหลายรอบ context ก็ยิ่งโตขึ้นเรื่อย ๆ ถ้าประเมิน token ผิดตั้งแต่ตอนนี้ พอถึงวันที่ 2 จะกะไม่ได้เลยว่าเหลือที่ให้ agent คิดต่ออีกกี่รอบก่อนชนขีดจำกัด

---

## Lab: นับ Token ของ Ticket เทียบกับ Config

### เป้าหมาย

เปรียบเทียบต้นทุน token ของข้อความสองประเภทที่ระบบนี้ต้องประมวลผลจริงทุกวัน — คำอธิบายปัญหาจากลูกค้า (ภาษาไทยล้วน) กับ running config ของอุปกรณ์ (ภาษาอังกฤษ/คำสั่งเทคนิคล้วน) — แล้วอธิบายว่าทำไมตัวเลขต่างกัน

### สิ่งที่ให้มา

- ตาราง `tickets` ใน PostgreSQL มีคอลัมน์ `title`, `description` เป็นภาษาไทย
- ตาราง `device_configs` มีคอลัมน์ `config_markdown` เป็น running config จริงที่แปลงเป็น Markdown แล้ว (ดู schema เต็มที่ `docker/postgres/init/02_schema.sql.template`)
- สิทธิ์ที่ใช้ดึงข้อมูล: บัญชี read-only `mcp_reader` ผ่าน `PG_DSN` ใน `.env.example` — งานนี้ทำแค่ `SELECT` จึงไม่ต้องใช้บัญชี admin
- ฟังก์ชัน `compare()` ใน `agent/tokenizer.py` ที่ใช้ไปแล้วด้านบน

### ขั้นตอน

```bash
uv run python - <<'PY'
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path("apps/agent-api")))

import psycopg
from agent.tokenizer import compare

PG_DSN = os.getenv(
    "PG_DSN",
    "postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb",
)

with psycopg.connect(PG_DSN) as conn:
    cur = conn.cursor()
    cur.execute("SELECT ticket_id, title, description FROM tickets ORDER BY ticket_id LIMIT 1")
    ticket_id, title, description = cur.fetchone()
    cur.execute("SELECT device_id, config_markdown FROM device_configs ORDER BY device_id LIMIT 1")
    device_id, config_markdown = cur.fetchone()

print(f"=== Ticket {ticket_id}: {title} ===")
ticket_stats = compare(description)
print(ticket_stats)

print(f"\n=== Config {device_id} ===")
config_stats = compare(config_markdown)
print(config_stats)

print("\n=== เทียบสัดส่วน ===")
print(f"tokens_per_word (ticket): {ticket_stats.get('tokens_per_word')}")
print(f"tiktoken_error_pct (ticket): {ticket_stats.get('tiktoken_error_pct')}%")
print(f"tiktoken_error_pct (config): {config_stats.get('tiktoken_error_pct')}%")
PY
```

โหลด `.env` ก่อนรันจริงถ้ายังไม่ได้ export ตัวแปรไว้ในเชลล์ (`export $(grep -v '^#' .env | xargs)` หรือใช้ `python-dotenv` ก็ได้ — ตัวอย่างข้างบนพึ่งค่า default ของ `PG_DSN` ตรง ๆ เพื่อความสั้น)

### ผลลัพธ์ที่ควรเห็น

```
=== Ticket TK-25-00001: อินเทอร์เน็ตหลุดเป็นช่วงๆ ตั้งแต่เมื่อวาน ===
{'text_length': 129, 'model_tokens': 70, 'tiktoken_tokens': 119, 'thai_words': 36, 'tiktoken_error_pct': 70.0, 'tokens_per_word': 1.94}

=== Config APE-BKK-05 ===
{'text_length': 185, 'model_tokens': 94, 'tiktoken_tokens': 82, 'thai_words': 73, 'tiktoken_error_pct': -12.8, 'tokens_per_word': 1.29}

=== เทียบสัดส่วน ===
tokens_per_word (ticket): 1.94
tiktoken_error_pct (ticket): 70.0%
tiktoken_error_pct (config): -12.8%
```

(ticket/config ที่ดึงมาได้ควรเป็นใบแรกตามลำดับ `ORDER BY ticket_id`/`device_id` เสมอสำหรับชุดข้อมูล seed เดียวกัน — ถ้าได้เลขต่างจากนี้ ให้ตรวจว่ากำลังต่อฐานข้อมูลชุดเดียวกับตัวอย่างนี้หรือไม่)

**วิธีอ่านผลลัพธ์นี้**:

- **ทิศทางของ error กลับกันระหว่างสองก้อนข้อความ**: ticket (ไทยล้วน) ได้ `+70.0%` (tiktoken นับ**เกิน**จริง) ส่วน config (อังกฤษ/คำสั่งเทคนิคล้วน) ได้ `-12.8%` (tiktoken นับ**ต่ำ**กว่าจริงเล็กน้อย) — ขนาดของความคลาดเคลื่อนต่างกันมาก (70.0 เทียบกับ 12.8) และเครื่องหมายยังตรงข้ามกันด้วย ตอบคำถามข้อ 2 ได้ตรงตัว
- `tokens_per_word` ของ ticket อยู่ที่ 1.94 (เกือบ 2 token ต่อคำไทย) สูงกว่า config ที่ 1.29 อย่างชัดเจน — สอดคล้องกับเหตุผลข้อ 1 ในหัวข้อ 3 ด้านล่าง ที่ว่าภาษาไทยไม่มีช่องว่างคั่นคำ
- ตัวเลขนี้มาจาก ticket **เพียง 1 ใบ**เท่านั้น — คำถามข้อ 3 ในหัวข้อ "สิ่งที่ต้องสังเกต" ด้านล่างให้ประมาณการทั้ง 120 ใบ ซึ่งต้องคูณค่าเฉลี่ยต่อใบเอง ไม่ใช่ใช้ตัวเลขจากใบเดียวนี้ตรงๆ (ตัวเลขต่อใบจะแกว่งไปตามความยาวและเนื้อหาของแต่ละ ticket)

### สิ่งที่ต้องสังเกตและอธิบายในผลลัพธ์

1. `model_tokens` ของ ticket description กับ config มีอัตราส่วนต่อความยาวตัวอักษรต่างกันอย่างไร
2. `tiktoken_error_pct` ของสองก้อนข้อความต่างกันมากน้อยแค่ไหน — ทำไม config (ภาษาอังกฤษ/คำสั่งล้วน) จึงมัก error น้อยกว่า ticket (ภาษาไทยล้วน)
3. ถ้าต้องส่ง ticket description ทั้งหมด 120 ใบ (ขนาด production จริงคือหลักพัน — ดู `day0/01-architecture.md` หัวข้อ 5) เข้า context เดียวกัน จะประเมิน token รวมผิดไปเท่าไรถ้าใช้ `tiktoken` แทน tokenizer จริง

### เกณฑ์ผ่าน

- [ ] รันสคริปต์สำเร็จ ได้ตัวเลข `model_tokens`, `tiktoken_tokens`, `thai_words` ครบทั้งสองก้อนข้อความ
- [ ] ระบุได้ว่า `tiktoken_error_pct` ของก้อนไหนสูงกว่า พร้อมเหตุผลเชิงภาษาศาสตร์ (ไม่ใช่แค่ก็อปตัวเลข)
- [ ] คำนวณ token รวมโดยประมาณของ ticket description ทั้ง 120 ใบ (คูณค่าเฉลี่ยต่อใบ) แล้วเทียบว่าคิดเป็นกี่เปอร์เซ็นต์ของ context window ที่ตั้งไว้ในระบบ (อ้างอิงจากค่า `context_tokens` ที่เคยเห็นตอนรัน `make demo`)

### สิ่งที่ต้องส่ง

- ผลลัพธ์ตัวเลขทั้งสามค่าของทั้งสองก้อนข้อความ (คัดลอกจาก terminal)
- คำอธิบายสั้น ๆ (2-3 บรรทัด) ว่าทำไมตัวเลขต่างกัน และมันหมายความว่าอย่างไรต่อการออกแบบ prompt ในโมดูลถัดไป

---

## ต่อไป

→ [Lab: Vector ใน PostgreSQL และ Neo4j](02-lab-pg-neo4j-vectors.md)
