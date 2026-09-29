# สรุป Day 1 · แก้ JSON Template ของ Agent จริงใน App

เสริม (ไม่บังคับ) · อ่านเมื่อใดก็ได้หลังจากเรียน Module 3 และ Workshop 1 แล้ว

---

## เหตุผลที่ควรทราบเรื่องนี้

Module 3 และ Workshop 1 สอนหลักการบังคับให้ LLM ตอบเป็น JSON ตาม schema ผ่าน Pydantic ร่วมกับ guided decoding และ auto-retry ด้วยมือตัวเอง อย่างไรก็ตาม `TicketExtraction` ที่เขียนขึ้นใน Workshop 1 เป็นไฟล์ lab แยกต่างหาก **ไม่ได้เชื่อมต่อกับ agent จริงที่รันอยู่ใน `apps/agent-api`** เอกสารนี้สรุปว่าหากต้องการแก้ไข JSON template ของ agent จริง (ตัวที่ Chainlit และ MCP Inspector เรียกใช้งานอยู่เป็นประจำ) ต้องแก้ไขที่ใด

---

## ไฟล์หลักที่ต้องทราบ: `apps/agent-api/schemas.py`

ทุก schema ที่ agent จริงบังคับให้ LLM ตอบตามรวมอยู่ในไฟล์นี้ไฟล์เดียว:

| Schema | ใช้ที่ไฟล์ | ทำหน้าที่ |
|---|---|---|
| `IntentResult` | `agent/intent.py` | จัดประเภทคำถามผู้ใช้ก่อนเข้า ReAct loop (Module 7 วันที่ 2) |
| `ReactDecision` | `agent/react.py` | หนึ่งรอบ Thought → Action ของ ReAct loop — รูปแบบเดียวกับ Workshop 1 |
| `StepResult` | `agent/react.py` | บันทึกผลแต่ละ step หลังเรียก tool |
| `GroundingVerdict` | `agent/grounding.py` | ตรวจสอบว่าคำตอบสุดท้ายมีหลักฐานรองรับจริงหรือไม่ |
| `TopicState` / `MemorySnapshot` | `agent/memory.py` | โครงสร้าง memory ข้ามเทิร์น |
| `ChatRequest` / `Usage` | `main.py` | รูปร่างของ request/response ใน REST API |

**ไม่มี schema ใดใน `apps/` ที่เกี่ยวข้องกับการสกัด ticket แบบ `TicketExtraction` ของ Workshop 1** — หากต้องการให้ agent จริงสกัด ticket ได้ในลักษณะเดียวกัน จำเป็นต้องเขียน schema ใหม่เพิ่มลงในไฟล์นี้เอง ระบบไม่มีให้โดยอัตโนมัติ

---

## กลไกเบื้องหลัง (หลักการเดียวกับ Module 3)

`apps/agent-api/agent/llm.py` → `complete_structured()` ทำงานตามหลักการเดียวกับที่ Module 3 สอนและ Workshop 1 ให้ฝึกเขียนเอง:

```python
json_schema = schema.model_json_schema()
kwargs["response_format"] = {
    "type": "json_schema",
    "json_schema": {"name": schema.__name__, "schema": json_schema, "strict": True},
}
```

เมื่อแก้ไข field ใน schema (`schemas.py`) ฟังก์ชัน `model_json_schema()` จะปรับปรุงข้อมูลโดยอัตโนมัติ และ guided decoding จะบังคับให้ LLM ตอบตามรูปแบบใหม่ทันที ไม่จำเป็นต้องแก้ไขส่วนอื่นเพิ่มเติม หากเป็นเพียงการเพิ่ม field ใหม่

---

## ตัวอย่างการแก้ไขจริง: เพิ่ม field `confidence` ให้ `ReactDecision`

**ก่อนแก้ไข** (`apps/agent-api/schemas.py`):

```python
class ReactDecision(BaseModel):
    thought: str = Field(description="...")
    tool: str | None = Field(default=None, description="...")
    arguments: dict = Field(default_factory=dict)
```

**หลังแก้ไข**:

```python
class ReactDecision(BaseModel):
    thought: str = Field(description="...")
    tool: str | None = Field(default=None, description="...")
    arguments: dict = Field(default_factory=dict)
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="ความมั่นใจของโมเดลต่อการตัดสินใจนี้ - หลักการเดียวกับ confidence ใน TicketExtraction ของ Workshop 1",
    )
```

เพียงเท่านี้ LLM จะต้องตอบ field `confidence` มาด้วยทุกรอบของ ReAct loop โดยถูกบังคับผ่าน guided decoding เช่นเดียวกับ Workshop 1

**อย่างไรก็ตาม field ใหม่นี้จะยังไม่ถูกนำไปใช้งานจริง** จนกว่าจะแก้ไข `apps/agent-api/agent/react.py` ให้อ่านค่านั้นด้วย ตัวอย่างเช่นบรรทัดนี้ (มีอยู่แล้วในโค้ด):

```python
yield EventType.THOUGHT, {"step": step_num, "thought": decision.thought, "tool": decision.tool}
```

แก้ไขเป็น:

```python
yield EventType.THOUGHT, {"step": step_num, "thought": decision.thought,
                          "tool": decision.tool, "confidence": decision.confidence}
```

นี่คือหลักการเดียวกับที่เกณฑ์ผ่านของ Workshop 1 ได้กล่าวถึง — การเพิ่ม field ใน schema เพียงอย่างเดียวยังไม่เพียงพอ ต้องมีโค้ดที่นำ field นั้นไปใช้งานจริงด้วย มิฉะนั้นค่าที่ได้จะเป็นเพียงข้อมูลที่ "มีอยู่" แต่ไม่ส่งผลใด ๆ ต่อการทำงานของระบบ

---

## ขั้นตอนหยุดและรันระบบใหม่เพื่อให้เห็นผลการแก้ไข

| service | คำสั่ง | รองรับ reload อัตโนมัติหรือไม่ |
|---|---|---|
| `apps/agent-api` (ไฟล์ที่มี `schemas.py`) | `make api` | ✅ มี `--reload` — บันทึกไฟล์แล้วเห็นผลทันที ไม่ต้อง restart เอง |
| `apps/chainlit-ui` | `make ui` | ✅ มี `-w` (watch mode) เช่นกัน |
| `apps/mcp-server` | `make mcp` | ❌ **ไม่มี reload flag** — ต้องกด `Ctrl+C` แล้วรันคำสั่งใหม่ทุกครั้งที่แก้ไขโค้ดส่วนนี้ |

**วิธีทดสอบว่าการแก้ไขได้ผลจริง**:

1. แก้ไข `schemas.py` (และ `react.py` หากต้องการใช้ field นั้นจริง) แล้วบันทึกไฟล์
2. ตรวจสอบ log ของ terminal ที่รัน `make api` ว่าปรากฏข้อความ `Reloading...` หรือ `Application startup complete` ใหม่หรือไม่ (หากไม่ auto-reload ให้ตรวจสอบว่ารันด้วย `--reload` จริงหรือไม่)
3. เปิด Chainlit ([http://localhost:8000](http://localhost:8000)) แล้วถามคำถามที่ต้องเข้า ReAct loop เช่น *"ทำไมช่วงนี้มีลูกค้าแจ้งเน็ตหลุดซ้ำๆ หลายราย"*
4. ตรวจสอบ event `THOUGHT` ที่ส่งออกมา (จาก log ฝั่ง `agent-api` หรือผ่าน MCP Inspector) ว่ามี field ใหม่ (`confidence`) ปรากฏจริงในแต่ละ step หรือไม่

หากแก้ไข schema แล้วยังไม่พบ field ใหม่ในผลลัพธ์ ให้ตรวจสอบตามลำดับดังนี้:

- โมเดลที่ใช้งานรองรับ guided decoding จริงหรือไม่ (`LLM_GUIDED_DECODING=true` ใน `.env`) — หากปิดอยู่ โมเดลอาจข้าม field ที่ไม่บังคับหรือระบุ type ไม่ถูกต้อง
- แก้ไข `schemas.py` ถูกไฟล์จริงหรือไม่ (มีเพียงไฟล์เดียว ไม่มีชุดซ้ำกันที่อื่น)
- ฝั่งที่แสดงผล (Chainlit/MCP Inspector) มีโค้ดสำหรับอ่าน field ใหม่แล้วหรือยัง (ค่าอาจถูกส่งมาถึงจริงแล้ว แต่ UI ยังไม่ได้แสดงผลออกมา)

---

## ความเชื่อมโยงกับเนื้อหา Day 1

- แนวคิด "schema คือสัญญาที่ LLM ต้องปฏิบัติตาม" = [Module 3](06-module3-json-api.md)
- แนวคิด "retry ด้วยการส่ง error message กลับไป แทนการสุ่มใหม่" ที่ `complete_structured()` ใช้งานจริง คือหลักการเดียวกับที่ฝึกเขียนเองใน [Workshop 1](07-workshop1-ticket-extractor.md)
- `ReactDecision` ที่ยกตัวอย่างข้างต้นคือ schema ตัวเดียวกับที่ [Module 5 วันที่ 2](../day2/03-module5-react-loop.md) ให้เขียน ReAct loop เองมาใช้งานจริง

---

## ต่อไป

→ [Module 4: ReAct Pattern](../day2/01-module4-react-pattern.md)
