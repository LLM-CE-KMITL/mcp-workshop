# ADR-006: Gateway แบบ OpenAI-compatible ที่สลับได้

- สถานะ: Accepted
- วันที่บันทึก: 2026-11-01 (บันทึกย้อนหลังจากโค้ดที่ใช้งานอยู่ ไม่ใช่เอกสารต้นฉบับของผู้ออกแบบ)
- ADR ที่เกี่ยวข้อง: [ADR-005](0005-three-layer-structured-output.md), [ADR-012](0012-docker-and-database-layout.md)

- **บริบท:** ต้องรันได้ทั้งบน OpenRouter (ค่าเริ่มต้นของผู้เรียน) และเซิร์ฟเวอร์ vLLM ภายใน NT (LLM, embedding, rerank แยกเครื่อง) โดยไม่แก้โค้ด
- **ตัดสินใจ:** ทุกอย่างคุยผ่าน OpenAI protocol เลือกปลายทางด้วย `.env` เท่านั้น และรองรับความต่างของ gateway ในจุดเดียว (`llm.py`): รวม system message เป็นก้อนเดียว (`_merge_system` เพราะ chat template ของ Qwen บน vLLM ปฏิเสธ system message ตัวที่สอง), ไม่ส่ง `max_tokens` โดยปริยาย, ไม่ส่ง `dimensions` ให้ embedding (เซิร์ฟเวอร์ bge-m3 ปฏิเสธ), มี `LLM_ENABLE_THINKING` สำหรับปิดโหมดคิด และแยก `EMBEDDING_API_KEY` ออกจาก `LLM_API_KEY` (ว่าง = ใช้ค่าของ LLM) ค่าเริ่มต้นใน `.env.example` เป็น OpenRouter เสมอ ชุด NT อยู่ที่ `.env.ex.nt`
- **ผลที่ตามมา:** (+) สลับผู้ให้บริการได้ด้วย `.env` และผู้เรียนเริ่มได้ด้วย key เดียว (−) ทุกตัวแปรใหม่ต้องเพิ่มใน compose ด้วย ([AGENTS.md หัวข้อ 2](../../AGENTS.md#2-คำสั่งที่ใช้บ่อย)) การปิดโหมดคิดได้ผลเฉพาะบางเซิร์ฟเวอร์ ห้ามใส่ key ของ OpenRouter ใน URL แบบ http ที่ไม่เข้ารหัส
