# ADR-005: Structured output 3 ชั้น

- สถานะ: Accepted
- วันที่บันทึก: 2026-11-01 (บันทึกย้อนหลังจากโค้ดที่ใช้งานอยู่ ไม่ใช่เอกสารต้นฉบับของผู้ออกแบบ)
- ADR ที่เกี่ยวข้อง: [ADR-006](0006-swappable-openai-compatible-gateway.md)

- **บริบท:** บาง gateway รับ `response_format` แล้วไม่บังคับจริง (พบกับ `qwen3-30b-a3b` ผ่าน OpenRouter) request สำเร็จแต่โมเดลตอบเป็นร้อยแก้วหรือใช้ field ผิด
- **ตัดสินใจ:** `complete_structured()` ใช้พร้อมกัน: (1) schema อยู่ใน prompt เสมอ (2) `response_format` แบบ json_schema เมื่อ `LLM_GUIDED_DECODING=true` และถอดออกถ้า gateway ไม่รองรับ (3) ตรวจด้วย Pydantic แล้วส่ง error กลับให้โมเดลแก้ สูงสุด 3 ครั้ง ([llm.py](../../apps/agent-api/agent/llm.py))
- **ผลที่ตามมา:** (+) ทนต่อ gateway ที่ไม่บังคับ schema และไม่ต้องรู้ว่า gateway รองรับหรือไม่ (−) prompt ยาวขึ้นทุกครั้ง การปิด `LLM_GUIDED_DECODING` อย่างเดียวไม่แก้ปัญหา เพราะ schema ยังต้องอยู่ใน prompt (เป็นสาเหตุของ error `ReactDecision` ขาด `thought` ที่เคยพบ)
