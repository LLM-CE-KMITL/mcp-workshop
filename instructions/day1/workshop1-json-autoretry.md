# Workshop 1 · โมดูลบังคับ JSON พร้อม Auto-retry

**14:45 – 16:00** (75 นาที)

---

## โจทย์

สร้างคลาสที่รับ input จากผู้ใช้ ส่งไปประมวลผลกับ LLM โดย **บังคับโครงสร้าง output ที่แน่นอน** และถ้าได้ JSON ที่ไม่ถูกต้อง ให้ **แก้ไขและลองใหม่อัตโนมัติ**

ผลงานชิ้นนี้จะถูกใช้ต่อในวันที่ 2 (สร้าง plan) และวันที่ 3 (structured output ของ MCP tool) จึงควรเขียนให้ใช้ซ้ำได้

---

## บริบทงานจริง

`ticket_messages` ในระบบเป็นข้อความอิสระที่ลูกค้าและเจ้าหน้าที่พิมพ์กันเอง ไทยปนอังกฤษ ไม่มีโครงสร้าง

ต้องแปลงให้เป็นข้อมูลที่ระบบใช้ต่อได้:

```json
{
  "category": "intermittent",
  "severity": "high",
  "affected_device": "LPE-NBI-11",
  "affected_site": "NBI",
  "summary_th": "ลูกค้าแจ้งเน็ตหลุดเป็นช่วง วันละหลายครั้ง",
  "customer_impact": "ใช้งาน video conference ไม่ต่อเนื่อง",
  "confidence": 0.85
}
```

---

## สิ่งที่ต้องสร้าง

### 1. Schema

```python
from enum import Enum
from pydantic import BaseModel, Field

class Category(str, Enum):
    LINK_DOWN = "link_down"
    INTERMITTENT = "intermittent"
    SLOW = "slow"
    CONFIG = "config"
    MAINTENANCE = "maintenance"
    INQUIRY = "inquiry"

class Severity(str, Enum):
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"

class TicketExtraction(BaseModel):
    category: Category
    severity: Severity
    affected_device: str | None = Field(None, description="รหัสอุปกรณ์ เช่น LPE-NBI-11 ถ้าไม่มีให้เป็น null")
    affected_site: str | None = Field(None, description="BKK หรือ NBI เท่านั้น")
    summary_th: str = Field(description="สรุปภาษาไทยไม่เกิน 2 ประโยค")
    customer_impact: str = Field(description="ผลกระทบต่อการใช้งานของลูกค้า")
    confidence: float = Field(ge=0.0, le=1.0)
```

### 2. คลาส `StructuredExtractor`

```python
class StructuredExtractor:
    def __init__(self, schema, model=None, max_retries=3, temperature=0.0): ...

    async def extract(self, text: str) -> ExtractionResult:
        """คืนผลลัพธ์พร้อมข้อมูลว่า retry ไปกี่ครั้งและเพราะอะไร"""
```

**ต้องมี**

| ความสามารถ | รายละเอียด |
|---|---|
| บังคับ schema | ใช้ guided decoding ถ้า gateway รองรับ |
| Auto-retry | ส่ง validation error กลับไปให้โมเดลแก้ |
| ทำความสะอาด output | ตัด ` ```json ` และคำนำที่โมเดลชอบใส่ |
| บันทึกความพยายาม | เก็บว่าแต่ละครั้งผิดอะไร |
| Fallback | เมื่อ retry ครบแล้วยังไม่ผ่าน **ห้าม crash** |
| นับ token | รายงาน token ที่ใช้ทั้งหมดรวมทุก retry |

### 3. ผลลัพธ์ที่คืน

```python
class ExtractionResult(BaseModel):
    ok: bool
    data: TicketExtraction | None
    attempts: int
    errors: list[str]
    total_tokens: int
    latency_ms: int
    fallback_used: bool = False
```

---

## ทดสอบกับข้อมูลจริง

```sql
SELECT t.ticket_id,
       string_agg(m.author_role || ': ' || m.message, E'\n' ORDER BY m.created_at) AS conversation
FROM tickets t JOIN ticket_messages m ON m.ticket_id = t.ticket_id
GROUP BY t.ticket_id LIMIT 20;
```

---

## เกณฑ์ผ่าน

- [ ] ประมวลผล ticket ทั้ง 20 ใบได้ JSON ที่ผ่าน validation ครบ
- [ ] ระบบไม่ crash แม้แต่ครั้งเดียว
- [ ] มี log ว่า retry กี่ครั้ง และแต่ละครั้งผิดเพราะอะไร
- [ ] รายงาน token ที่ใช้รวม
- [ ] มี fallback เมื่อ retry ครบ

---

## โบนัส

1. **วัดผลของ guided decoding** — รันด้วย `LLM_GUIDED_DECODING=true` และ `false` อย่างละ 20 ครั้ง เทียบอัตราสำเร็จครั้งแรกและ token ที่ใช้
2. **เทียบโมเดล** — `gemma3:4b` กับ `gemma3:27b` ตัวเล็กพลาดบ่อยกว่ากี่เท่า
3. **ตรวจความสมเหตุสมผลข้ามฟิลด์** — ถ้า `affected_device = "LPE-NBI-11"` แต่ `affected_site = "BKK"` ต้องจับได้ (ใช้ Pydantic `model_validator`)

---

<details>
<summary>Hint</summary>

- ดูโครงที่ `apps/agent-api/agent/llm.py` → `complete_structured()` แต่**อย่าลอกทั้งดุ้น** เขียนเองแล้วค่อยเทียบ
- ตัด markdown fence: `if raw.startswith("```"): raw = raw.split("```")[1]` แล้วตัด `json` ที่ขึ้นต้น
- Pydantic ให้ error ที่อ่านรู้เรื่องอยู่แล้ว ส่ง `str(exc)` กลับไปได้เลย
- fallback ที่ดี: คืน object ที่ `confidence=0.0` และใส่ข้อความดิบไว้ใน `summary_th`
</details>

---

## สิ่งที่ต้องส่ง

`workshop1_extractor.py` + ผลรัน 20 ใบ + สรุปสถิติ retry
