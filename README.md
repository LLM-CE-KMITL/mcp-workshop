# แผนที่หลักสูตร — AI × IP-MPLS Workshop (3 วัน)

หน้านี้คือ**จุดเริ่มต้นเดียว**ของหลักสูตร ไล่ลิงก์ตามลำดับนี้ตั้งแต่บนลงล่างแล้วจะไม่หลง
แต่ละบรรทัดมีเวลาเรียนกำกับไว้ตรงกับตารางจริง ถ้าหลุดตาราง ให้กลับมาเปิดหน้านี้เพื่อดูว่าอยู่จุดไหน

> ภาพรวมสถาปัตยกรรม, model stack และการ map กับ production อยู่ที่ [README2.md](README2.md) —
> เปิดที่นั่นก่อนถ้ายังไม่เคยเห็นภาพรวมทั้งระบบ

---

## ก่อนวันอบรม

| ลำดับ | เอกสาร | ใช้ทำอะไร |
|---|---|---|
| 1 | [day0/01-prerequisites.md](INSTRUCTIONS/day0/01-prerequisites.md) | สิ่งที่ต้องเตรียมตัวก่อนมาเรียน |
| 2 | [day0/02-setup.md](INSTRUCTIONS/day0/02-setup.md) | ติดตั้งและตรวจสอบระบบด้วยตัวเอง |
| 3 | [day0/03-architecture.md](INSTRUCTIONS/day0/03-architecture.md) | ภาพรวมสถาปัตยกรรม + ตารางเวลาเต็ม 3 วัน |

---

## วันที่ 1 — ควบคุม LLM ผ่านโค้ด

| เวลา | เอกสาร |
|---|---|
| 09:00–10:30 | [day1/01-module1-tokenomics-embeddings.md](INSTRUCTIONS/day1/01-module1-tokenomics-embeddings.md) — Tokenomics & Vector Embeddings |
| 09:50–10:30 | [day1/02-lab1-add-vector-column.md](INSTRUCTIONS/day1/02-lab1-add-vector-column.md) — Lab 1: สร้าง Vector Column ด้วยตัวเอง |
| 10:45–11:35 | [day1/03-module2-transformer.md](INSTRUCTIONS/day1/03-module2-transformer.md) — โครงสร้างการทำงานของ Transformer |
| 11:35–12:00 | [day1/04-challenge1-thai-token-audit.md](INSTRUCTIONS/day1/04-challenge1-thai-token-audit.md) — โจทย์ 1: Thai Token Audit |
| 13:00–14:30 | [day1/05-module3-structured-output.md](INSTRUCTIONS/day1/05-module3-structured-output.md) — API ขั้นสูงและ Structured Output |
| 14:45–16:00 | [day1/06-workshop1-json-autoretry.md](INSTRUCTIONS/day1/06-workshop1-json-autoretry.md) — Workshop 1: บังคับ JSON พร้อม Auto-retry |
| 16:00–16:30 | [day1/07-challenge2-schema-under-pressure.md](INSTRUCTIONS/day1/07-challenge2-schema-under-pressure.md) — โจทย์ 2: Schema Under Pressure |
| เสริม/การบ้าน | [day1/08-lab-ingestion-markdown.md](INSTRUCTIONS/day1/08-lab-ingestion-markdown.md) — Lab เสริม: Ingestion Pipeline (ต่อจาก Lab 1) |

**เฉลยวันที่ 1**: [solutions/day1/](solutions/day1/) และ [solutions/challenges/](solutions/challenges/) — เปิดหลังจากลองเองแล้วเท่านั้น

---

## วันที่ 2 — เขียน Agent Loop เอง

| เวลา | เอกสาร |
|---|---|
| 09:00–10:30 | [day2/01-module4-react-memory.md](INSTRUCTIONS/day2/01-module4-react-memory.md) — วิธีคิดของ Agent (ReAct Pattern) |
| 10:45–11:35 | [day2/02-module5-function-calling.md](INSTRUCTIONS/day2/02-module5-function-calling.md) — Function Calling & Tool Definition |
| 11:35–12:00 | [day2/03-challenge3-tool-description-battle.md](INSTRUCTIONS/day2/03-challenge3-tool-description-battle.md) — โจทย์ 3: Tool Description Battle |
| 13:00–13:45 | [day2/04-module6-multi-agent.md](INSTRUCTIONS/day2/04-module6-multi-agent.md) — Multi-Agent & Orchestration Patterns |
| 13:45–14:10 | [day2/05-lab2-intent-gate.md](INSTRUCTIONS/day2/05-lab2-intent-gate.md) — Lab 2: Intent Gate |
| 14:10–14:30 | [day2/06-lab3-context-memory.md](INSTRUCTIONS/day2/06-lab3-context-memory.md) — Lab 3: Context Memory และการตรวจจับเปลี่ยนเรื่อง |
| 14:45–16:00 | [day2/07-workshop2-agent-loop.md](INSTRUCTIONS/day2/07-workshop2-agent-loop.md) — Workshop 2: เขียน Agent Loop ด้วยตัวเอง |
| 16:00–16:30 | [day2/08-challenge4-topic-shift-survival.md](INSTRUCTIONS/day2/08-challenge4-topic-shift-survival.md) — โจทย์ 4: Topic Shift Survival |
| เสริม | [day2/09-lab-grounding-verification.md](INSTRUCTIONS/day2/09-lab-grounding-verification.md) — Lab เสริม: Grounding ตรวจคำตอบก่อนส่งออก |

**เฉลยวันที่ 2**: [solutions/day2/](solutions/day2/) และ [solutions/challenges/](solutions/challenges/) — เปิดหลังจากลองเองแล้วเท่านั้น

---

## วันที่ 3 — MCP Production

| เวลา | เอกสาร |
|---|---|
| 09:00–10:15 | [day3/01-module7-mcp-architecture.md](INSTRUCTIONS/day3/01-module7-mcp-architecture.md) — สถาปัตยกรรมเชิงลึกของ MCP |
| 10:15–10:30 | [day3/02-lab4-jsonrpc-inspect.md](INSTRUCTIONS/day3/02-lab4-jsonrpc-inspect.md) — Lab 4: ดู JSON-RPC ที่วิ่งจริง |
| 10:45–11:35 | [day3/03-module8-security-sdk.md](INSTRUCTIONS/day3/03-module8-security-sdk.md) — ความปลอดภัยและการเลือก SDK |
| 11:35–12:00 | [day3/04-challenge5-guardrail-redteam.md](INSTRUCTIONS/day3/04-challenge5-guardrail-redteam.md) — โจทย์ 5: Guardrail Red-team (ทำเป็นคู่) |
| 13:00–14:00 | [day3/05-workshop3a-mcp-server.md](INSTRUCTIONS/day3/05-workshop3a-mcp-server.md) — Workshop 3A: สร้าง MCP Server ของตัวเอง |
| 14:00–14:30 | [day3/06-workshop3b-agent-api.md](INSTRUCTIONS/day3/06-workshop3b-agent-api.md) — Workshop 3B: ห่อ Agent เป็น API |
| 14:30–14:45 | [day3/07-workshop3c-chainlit.md](INSTRUCTIONS/day3/07-workshop3c-chainlit.md) — Workshop 3C: ต่อ Chainlit เข้ากับ Agent API |
| 14:45–15:00 | [day3/08-workshop3d-connect-clients.md](INSTRUCTIONS/day3/08-workshop3d-connect-clients.md) — Workshop 3D: ต่อกับ Claude Desktop / Claude Code / Cursor |
| แทรกช่วง WS3/สรุป | [day3/09-lab5-vector-store-comparison.md](INSTRUCTIONS/day3/09-lab5-vector-store-comparison.md) — Lab 5: เทียบ Vector Store ทั้ง 3 ตัว |
| แทรกช่วง WS3/สรุป | [day3/10-lab6-rerank-pipeline.md](INSTRUCTIONS/day3/10-lab6-rerank-pipeline.md) — Lab 6: Retrieve → Rerank → Generate |
| เสริม | [day3/11-lab-elicitation.md](INSTRUCTIONS/day3/11-lab-elicitation.md) — Lab: Elicitation (ฟีเจอร์ MCP spec 2025-06-18) |
| 15:00–15:30 | [day3/12-challenge6-cross-service-diagnosis.md](INSTRUCTIONS/day3/12-challenge6-cross-service-diagnosis.md) — โจทย์ 6: Cross-Service Diagnosis (โจทย์ใหญ่สุด) |
| ช่วงสรุป (15 นาที) | [day3/13-scale-notes.md](INSTRUCTIONS/day3/13-scale-notes.md) — บันทึกเรื่อง Scale: 10 อุปกรณ์ vs 2,600 อุปกรณ์ |
| 15:30–16:30 | [day3/14-wrap-up-mpls-llm.md](INSTRUCTIONS/day3/14-wrap-up-mpls-llm.md) — สรุปผลการอบรม และแบ่งงานสำหรับ MPLS LLM |

**เฉลยวันที่ 3**: ไม่มีไฟล์แยก — โค้ดจริงใน [apps/mcp-server/](apps/mcp-server/) และ [apps/agent-api/](apps/agent-api/)
**คือ**เฉลย อ่านเหตุผลที่ [solutions/day3/README.md](solutions/day3/README.md)

---

## หลังอบรม — เอกสารอ้างอิง (เปิดใช้เมื่อจำเป็น ไม่ต้องอ่านตามลำดับ)

| เอกสาร | ใช้เมื่อไหร่ |
|---|---|
| [reference/cheatsheet.md](INSTRUCTIONS/reference/cheatsheet.md) | สรุปคำสั่ง/โค้ดที่ใช้บ่อยทั้งหลักสูตร |
| [reference/troubleshooting.md](INSTRUCTIONS/reference/troubleshooting.md) | ระบบรันไม่ผ่าน / error ที่เจอบ่อย |
| [reference/model-stack.md](INSTRUCTIONS/reference/model-stack.md) | รายละเอียดโมเดลแต่ละตัวและบทบาท |
| [reference/local-llm-ollama-vllm.md](INSTRUCTIONS/reference/local-llm-ollama-vllm.md) | ตั้งค่า Ollama/vLLM เอง หรือย้ายไป production |
| [reference/sdk-comparison.md](INSTRUCTIONS/reference/sdk-comparison.md) | ทำไมเลือกเขียนเองแทน LangChain/ADK |
| [reference/evaluation-metrics.md](INSTRUCTIONS/reference/evaluation-metrics.md) | วัดผลคุณภาพคำตอบ agent |
| [reference/prompt-examples.md](INSTRUCTIONS/reference/prompt-examples.md) | ตัวอย่าง prompt ที่ใช้สาธิตในห้อง |
| [reference/production-mapping.md](INSTRUCTIONS/reference/production-mapping.md) | เทียบ workshop กับระบบ production จริง (ใช้ตอนติดตามผล 30/60/90 วัน) |

---

## สำหรับวิทยากร/ทีมสนับสนุน

- [CHECKLIST.md](CHECKLIST.md) — เช็คลิสต์เตรียมงานตั้งแต่ T-7 วันถึงวันจริง
