# ADR (Architecture Decision Records)

บันทึกเหตุผลเบื้องหลังการตัดสินใจเชิงสถาปัตยกรรมของโครงการ แต่ละไฟล์มีหนึ่งการตัดสินใจ
ภาพรวมของ repo อยู่ที่ [AGENTS.md](../../AGENTS.md)

## รูปแบบ

- **สถานะ:** Accepted (เป็นสิ่งที่โค้ดทำอยู่ปัจจุบัน) / Superseded (ถูกแทนที่ ให้ระบุ ADR ใหม่) / Proposed (ยังไม่ตัดสินใจ)
- **บริบท:** ปัญหาหรือแรงกดดันที่ทำให้ต้องตัดสินใจ
- **ตัดสินใจ:** สิ่งที่เลือกและตำแหน่งในโค้ด
- **ผลที่ตามมา:** ข้อดี (+) และข้อเสีย (−) ที่ต้องยอมรับ

ถ้าต้องเปลี่ยนการตัดสินใจ ให้เพิ่ม ADR ฉบับใหม่ที่ระบุว่าแทนฉบับเดิม และแก้สถานะของฉบับเดิมเป็น Superseded แทนการเขียนทับเนื้อหา

## รายการ

| ADR | หัวข้อ |
|---|---|
| [001](0001-react-loop-instead-of-planner-executor.md) | ReAct loop แทน planner/executor |
| [002](0002-code-enforced-layered-guardrails.md) | Guardrail บังคับด้วยโค้ดหลายชั้น |
| [003](0003-data-derived-now-and-relative-ranges.md) | "ตอนนี้" มาจากข้อมูล และใช้ช่วงเวลาสัมพัทธ์เท่านั้น |
| [004](0004-single-mcp-server-in-process-default.md) | เข้าถึงข้อมูลผ่าน MCP server เดียว (in-process เป็นค่าเริ่มต้น) |
| [005](0005-three-layer-structured-output.md) | Structured output 3 ชั้น |
| [006](0006-swappable-openai-compatible-gateway.md) | Gateway แบบ OpenAI-compatible ที่สลับได้ |
| [007](0007-two-layer-intent-gate.md) | Intent Gate สองชั้น |
| [008](0008-topic-shift-memory-with-summaries.md) | Memory แบบตรวจการเปลี่ยนหัวข้อและสรุป |
| [009](0009-regex-grounding-instead-of-llm-judge.md) | Grounding แบบ regex แทน LLM-judge |
| [010](0010-scenario-first-deterministic-dataset.md) | ชุดข้อมูลแบบ scenario-first และ seed แบบกำหนดผลได้ |
| [011](0011-tool-docstring-as-selection-contract.md) | docstring ของ tool คือสัญญาการเลือก tool |
| [012](0012-docker-and-database-layout.md) | โครงสร้าง Docker และฐานข้อมูล |
| [013](0013-demo-app-separate-from-learner-ui.md) | แอปเดโมแยกจาก UI ของผู้เรียน |
| [014](0014-redact-secrets-at-tool-output.md) | ปิดบังความลับที่ขอบเขตขาออกของ tool |
