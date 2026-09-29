# แผนที่หลักสูตร — AI × IP-MPLS Workshop (3 วัน)

หน้านี้คือ**จุดเริ่มต้นเดียว**ของหลักสูตร ควรไล่ตามลิงก์ในลำดับนี้ตั้งแต่บนลงล่างเพื่อไม่ให้หลงทาง
แต่ละบรรทัดมีเวลาเรียนกำกับไว้ตรงกับตารางจริง หากหลุดจากตาราง ให้กลับมาเปิดหน้านี้เพื่อตรวจสอบว่าอยู่จุดใด

> ภาพรวมสถาปัตยกรรม, model stack และการเทียบกับ production อยู่ที่ [README2.md](README2.md) —
> ควรเปิดอ่านที่นั่นก่อน หากยังไม่เคยเห็นภาพรวมทั้งระบบ

---

## ก่อนวันอบรม

| ลำดับ | เอกสาร | ใช้ทำอะไร |
|---|---|---|
| 1 | [day0/01-architecture.md](INSTRUCTIONS/day0/01-architecture.md) | ภาพรวมสถาปัตยกรรม (ตารางเวลาเต็ม 3 วันอยู่ในหน้านี้ ด้านล่าง) |
| 2 | [day0/02-initial-data.md](INSTRUCTIONS/day0/02-initial-data.md) | ตัวอย่างข้อมูลจริงใน 3 ฐานข้อมูลหลัง seed (PostgreSQL/Neo4j/OpenSearch) |
| 3 | [day0/03-prerequisites.md](INSTRUCTIONS/day0/03-prerequisites.md) | สิ่งที่ต้องเตรียมตัวก่อนมาเรียน |
| 4 | [day0/04-full-demo.md](INSTRUCTIONS/day0/04-full-demo.md) | ลองรันทั้งระบบให้จบใน 10 นาที ก่อนเริ่มเรียนจริง (ไม่บังคับ) |
| 5 | [day0/05-setup.md](INSTRUCTIONS/day0/05-setup.md) | ติดตั้งและตรวจสอบระบบด้วยตัวเอง |

---

## วันที่ 1 — LLM พื้นฐานและการค้นหาเชิงความหมาย

| เวลา | เอกสาร |
|---|---|
| ก่อนเริ่ม | [day1/00-day1-overview.md](INSTRUCTIONS/day1/00-day1-overview.md) — ภาพรวมกิจกรรมทั้งวัน: อะไรต่อกับอะไร ตรงไหนต้องลงมือเขียนโค้ด (อ่านก่อนเข้าโมดูลแรก) |
| 09:00–10:15 | [day1/01-module1-llm-basics.md](INSTRUCTIONS/day1/01-module1-llm-basics.md) — Module 1: LLM ทำงานอย่างไร (Token, ค่าใช้จ่าย, Context Window) |
| 10:30–11:05 | [day1/02-lab-pg-vectors.md](INSTRUCTIONS/day1/02-lab-pg-vectors.md) — Lab: Vector ใน PostgreSQL |
| 11:05–11:30 | [day1/03-lab-neo4j-vectors.md](INSTRUCTIONS/day1/03-lab-neo4j-vectors.md) — Lab: Vector ใน Neo4j |
| 11:30–12:30 | [day1/04-module2-embeddings-opensearch.md](INSTRUCTIONS/day1/04-module2-embeddings-opensearch.md) — Module 2: Embeddings กับ OpenSearch |
| 12:30–13:00 | [day1/05-lab-ingestion-markdown.md](INSTRUCTIONS/day1/05-lab-ingestion-markdown.md) — Lab: Ingestion Pipeline สำหรับเอกสาร Markdown |
| 14:00–15:00 | [day1/06-module3-json-api.md](INSTRUCTIONS/day1/06-module3-json-api.md) — Module 3: เรียก API และให้ตอบเป็น JSON |
| 15:15–16:30 | [day1/07-workshop1-ticket-extractor.md](INSTRUCTIONS/day1/07-workshop1-ticket-extractor.md) — Workshop 1: ตัวแยกข้อมูล Ticket |
| เสริม (ไม่บังคับ) | [day1/08-summary-json-template-in-app.md](INSTRUCTIONS/day1/08-summary-json-template-in-app.md) — สรุป: แก้ JSON Template ของ Agent จริงใน App ต้องแก้ไฟล์ไหน ตัวอย่างการแก้ และต้อง stop/run อะไรถึงเห็นผล |

**เฉลยวันที่ 1**: [solutions/day1/](solutions/day1/) — เปิดหลังจากลองเองแล้วเท่านั้น

---

## วันที่ 2 — ReAct Agent วิเคราะห์เหตุเสีย

| เวลา | เอกสาร |
|---|---|
| ก่อนเริ่ม | [day2/00-day2-overview.md](INSTRUCTIONS/day2/00-day2-overview.md) — ภาพรวมกิจกรรมทั้งวัน: อะไรต่อกับอะไร ตรงไหนต้องลงมือเขียนโค้ด (อ่านก่อนเข้าโมดูลแรก) |
| 09:00–10:00 | [day2/01-module4-react-pattern.md](INSTRUCTIONS/day2/01-module4-react-pattern.md) — Module 4: ReAct Pattern |
| 10:00–10:30 | [day2/02-module7-intent-gate.md](INSTRUCTIONS/day2/02-module7-intent-gate.md) — Module 7: Intent Gate |
| 10:45–12:00 | [day2/03-module5-react-loop.md](INSTRUCTIONS/day2/03-module5-react-loop.md) — Module 5: เขียน ReAct Loop เอง |
| 13:00–14:15 | [day2/04-module6-tools-3-databases.md](INSTRUCTIONS/day2/04-module6-tools-3-databases.md) — Module 6: เครื่องมือจาก 3 ฐานข้อมูล |
| 14:15–14:45 | [day2/05-module8-memory.md](INSTRUCTIONS/day2/05-module8-memory.md) — Module 8: Memory |
| 15:00–16:30 | [day2/06-workshop2-noc-agent.md](INSTRUCTIONS/day2/06-workshop2-noc-agent.md) — Workshop 2: ReAct Agent สำหรับ NOC |

**เฉลยวันที่ 2**: [solutions/day2/](solutions/day2/) — เปิดหลังจากลองเองแล้วเท่านั้น

---

## วันที่ 3 — MCP Server สำหรับงาน MPLS

| เวลา | เอกสาร |
|---|---|
| ก่อนเริ่ม | [day3/00-day3-overview.md](INSTRUCTIONS/day3/00-day3-overview.md) — ภาพรวมกิจกรรมทั้งวัน: อะไรต่อกับอะไร ตรงไหนต้องลงมือเขียนโค้ด (อ่านก่อนเข้าโมดูลแรก) |
| 09:00–10:30 | [day3/01-module9-mcp-intro.md](INSTRUCTIONS/day3/01-module9-mcp-intro.md) — Module 9: MCP คืออะไร (Tools, Resources, Prompts) |
| 10:45–12:00 | [day3/02-module10-security-basics.md](INSTRUCTIONS/day3/02-module10-security-basics.md) — Module 10: ความปลอดภัยพื้นฐาน |
| 13:00–16:30 | [day3/03-workshop3-mpls-noc-mcp-server.md](INSTRUCTIONS/day3/03-workshop3-mpls-noc-mcp-server.md) — Workshop 3: MPLS NOC MCP Server (13:00–15:30 ลงมือทำ, 15:30–16:30 สรุปและถาม-ตอบ) |

**เฉลยวันที่ 3**: [solutions/day3/](solutions/day3/) — `apps/mcp-server/` เป็นตัวอย่างสาธิตอ้างอิง ส่วนเฉลยของไฟล์ที่ต้องเขียนเองอยู่ที่ [solutions/day3/workshop3_mcp_server.py](solutions/day3/workshop3_mcp_server.py) — เปิดหลังจากลองเองแล้วเท่านั้น

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
