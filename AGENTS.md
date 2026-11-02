# AGENTS.md

เอกสารสำหรับ AI coding agent และผู้พัฒนาที่เข้ามาทำงานใน repo นี้ สรุปว่าระบบคืออะไร รันอย่างไร โครงสร้างเป็นอย่างไร กติกาที่ต้องรักษา ปัญหาที่ทราบแล้ว และเหตุผลเบื้องหลังการตัดสินใจเชิงสถาปัตยกรรม (ADR)

> **ที่มาของเนื้อหา:** ถอดความจากโค้ด คอมเมนต์ในโค้ด และการตัดสินใจระหว่างการทำงานร่วมกัน ณ วันที่ 2026-11-01
> ADR ด้านล่างเป็นบันทึก**ย้อนหลัง** ไม่ใช่เอกสารต้นฉบับของผู้ออกแบบ ถ้าโค้ดกับเอกสารนี้ขัดกัน ให้เชื่อโค้ดแล้วแก้เอกสารนี้

---

## 1. โครงการนี้คืออะไร

หลักสูตร 3 วัน **AI × IP-MPLS Workshop** สอนสร้าง AI Agent และ MCP Server สำหรับงานดูแลเครือข่าย IP-MPLS ของ NT โดยเขียนกลไกเองไม่พึ่ง framework เนื้อหาหลักสูตรเขียนเป็น**ภาษาไทย** ส่วนโค้ดและคอมเมนต์ส่วนใหญ่เป็นภาษาอังกฤษ

- **ผลลัพธ์ปลายทาง:** MCP Server ที่ต่อ PostgreSQL + Neo4j + OpenSearch และ Agent ที่วางแผนเองว่าจะดึงข้อมูลจากที่ไหน พร้อม UI
- **ผู้ใช้เอกสารหลักสูตร:** ผู้เรียน (ลงมือเขียนบางไฟล์เอง) และวิทยากร (มีเฉลยใน `solutions/` และ `data/scenarios.md`)
- **จุดเริ่มต้นของหลักสูตร:** [README.md](README.md) (แผนที่หลักสูตร) และ [README2.md](README2.md) (ภาพรวมสถาปัตยกรรม)

---

## 2. คำสั่งที่ใช้บ่อย

ต้องมี `uv` และ Docker ค่า Python คือ 3.12 ([.python-version](.python-version))

```bash
cp .env.example .env          # ครั้งแรกเท่านั้น แล้วใส่ LLM_API_KEY (ห้ามรันซ้ำ จะทับ key เดิม)
make install                  # uv sync --all-extras
make up                       # เปิด 3 ฐานข้อมูล + pgAdmin + MailHog + dashboards แล้ว seed
make verify                   # ตรวจ 3 ฐานข้อมูลและ LLM endpoint
make api                      # Agent API   :8080  (uvicorn --reload)
make ui                       # Chainlit    :8000
make mcp                      # MCP server  :9000 (ใช้เมื่อต้องการโหมด http)
make demo                     # แอปเดโมใน container :8100 (UI) / :8180 (API) ใช้ --build เสมอ
make test                     # pytest -v
make lint                     # ruff check .
make eval                     # วัดคุณภาพคำตอบ (ต้อง make api ก่อน)
make reseed                   # ล้างและ seed ใหม่ (เวลาของข้อมูลเลื่อนตามปัจจุบัน)
```

กฎที่ต้องจำ:
- **แอปเดโมต้อง build ใหม่หลังแก้โค้ด** เพราะ image ฝังโฟลเดอร์ `apps/` ไว้ตอน build (`COPY apps/`) ถ้าไม่ใส่ `--build` จะได้โค้ดเก่า
- **เพิ่มตัวแปรสภาพแวดล้อมใหม่ต้องเพิ่มใน `docker/docker-compose.yml` ด้วย** เพราะ compose ส่งตัวแปรให้ `mcp-demo` และ `seeder` ทีละตัว ไม่ได้ส่งทั้ง `.env`
- เทสต์ที่ต้องใช้บริการจริงจะ **skip** (ไม่ fail) เมื่อบริการไม่ได้เปิด (ดู `needs_postgres`, `needs_neo4j`, `needs_opensearch`, `needs_llm` ใน [tests/conftest.py](tests/conftest.py)) จึงรันบนเครื่องเปล่าได้
- init script ของ Postgres รันเฉพาะตอน volume ว่าง ถ้าแก้สคริปต์ต้อง `make reset` (ลบ volume) จึงจะมีผล
- Windows: ไฟล์ `.sh` ที่เป็น CRLF ทำให้ `02_schema.sh` ล้ม ใช้ `uv run python scripts/fix_line_endings.py` (`--check` ตรวจอย่างเดียว, `--reset-db` ล้างฐานข้อมูลด้วย)

### พอร์ต

| บริการ | พอร์ต | บริการ | พอร์ต |
|---|---|---|---|
| Chainlit (ผู้เรียน) | 8000 | pgAdmin | 5050 |
| Agent API | 8080 | OpenSearch / Dashboards | 9200 / 5601 |
| MCP server | 9000 | Neo4j Browser / Bolt | 7474 / 7687 |
| เดโม UI / API | 8100 / 8180 | MailHog Web / SMTP | 8025 / 1025 |
| PostgreSQL | 5432 | Ollama / rerank (profile `llm`) | 11434 / 7997 |

---

## 3. โครงสร้าง repo

| ที่ | หน้าที่ |
|---|---|
| `apps/agent-api/` | Agent (FastAPI + SSE) แกนคือ `main.py` และ `agent/` |
| `apps/mcp-server/` | MCP server: `tools/`, `resources/`, `prompts/`, `security/`, `clock.py`, `config.py`, `db.py` (รายละเอียด tool อยู่ใน [TOOLS.md](apps/mcp-server/TOOLS.md)) |
| `apps/chainlit-ui/` | UI ของผู้เรียน (`app.py`, `elements.py`) |
| `apps/demo-app/` | UI ของเดโม: starters, health banner, replay mode |
| `docker/` | compose, seeder, loader, init script ของ Postgres/Neo4j/OpenSearch, image ของเดโม |
| `data/` | `scenarios.md` (Scenario Bible), ชุดคำถาม, fixture, log ตัวอย่าง |
| `INSTRUCTIONS/` | เอกสารหลักสูตร day0–day3 และ `reference/` |
| `solutions/` | เฉลย (ผู้เรียนเปิดหลังลองเองเท่านั้น) |
| `tests/`, `eval/` | เทสต์ และการวัดคุณภาพ (L0–L7) |
| `scripts/` | embed/ingest/เปรียบเทียบ vector store, `fix_line_endings.py` |

ไฟล์ที่ root เช่น `cosine.py`, `my_embed.py`, `ticket_opensearch_lab.py`, `workshop1_extractor.py` เป็นไฟล์ทดลองหรือ lab ที่ยังไม่ commit ส่วน `audit.log` และ `temp_reports/` เป็นผลลัพธ์ที่ระบบสร้าง

---

## 4. สถาปัตยกรรม

### 4.1 การไหลของหนึ่งเทิร์น ([apps/agent-api/main.py](apps/agent-api/main.py) `run_turn`)

```
ผู้ใช้ → Chainlit ─HTTP+SSE→ Agent API
   1. Intent Gate     fast path (regex) → ถ้าไม่ชัด ถาม LLM จัดป้าย 4 แบบ
      └ out_of_scope / needs_clarification → จบเทิร์น ไม่แตะ tool
   2. Memory          ตรวจการเปลี่ยนหัวข้อ → สรุปหัวข้อเก่าเก็บ archive
      └ general_knowledge → ตอบตรงๆ ไม่ใช้ tool
   3. ReAct loop      Thought → Action(tool) → Observation ทีละขั้น (LoopGuard)
   4. Synthesizer     เขียนคำตอบภาษาไทยจากหลักฐาน (stream)
   5. Grounding       ตรวจคำตอบกับหลักฐาน (verifier.py แบบ regex)
```

ลำดับ event ที่ UI ได้รับ ([events.py](apps/agent-api/agent/events.py)):
`intent_checked → memory_updated → (topic_changed) → thought → [step_started → step_result]* → grounding_checked → token* → usage → done` (มี `error` ได้ทุกจุด) ไม่มี event `plan_created` เพราะไม่มีขั้นวางแผนล่วงหน้า

### 4.2 ส่วนประกอบของ agent

| ส่วน | ไฟล์ | สาระสำคัญ |
|---|---|---|
| Intent Gate | [agent/intent.py](apps/agent-api/agent/intent.py) | ป้าย `in_scope`, `general_knowledge`, `needs_clarification`, `out_of_scope` ถ้าคำถามอ้างถึงบทสนทนาก่อนหน้าให้ถือเป็น `in_scope` |
| Memory | [agent/memory.py](apps/agent-api/agent/memory.py) | เก็บใน RAM ต่อ session ตรวจเปลี่ยนหัวข้อด้วย embedding (เกณฑ์ `MEMORY_TOPIC_SHIFT_THRESHOLD=0.3`) หรือวลีชัดเจน เช่น "เปลี่ยนเรื่อง" หน้าต่างบทสนทนา `MEMORY_WINDOW_TURNS=6` ส่วน [memory_longterm.py](apps/agent-api/agent/memory_longterm.py) เก็บระยะยาวใน pgvector คนละตาราง |
| ReAct | [agent/react.py](apps/agent-api/agent/react.py) | ทุกรอบเรียก `complete_structured(ReactDecision)` ได้ `{thought, tool, arguments}` ตั้ง `tool=null` เมื่อพร้อมตอบ ใส่ system prompt + รายการ tool + `clock://now` + บทสนทนาที่ผ่านมา |
| LoopGuard | react.py | หยุดเมื่อเกิน `AGENT_MAX_STEPS=8`, เรียก tool เดิมเกิน `AGENT_MAX_SAME_TOOL_CALLS=3`, หรือเรียกซ้ำด้วยอาร์กิวเมนต์เดิม |
| Synthesizer | [agent/synthesizer.py](apps/agent-api/agent/synthesizer.py) | ตอบภาษาไทย อ้างแหล่งข้อมูลทุกข้อเท็จจริง ต้องระบุ device ID ตรงตัวเมื่อหลักฐานชี้ต้นเหตุ ใช้ผล step ไม่เกิน 6,000 ตัวอักษรต่อ step |
| Grounding | [verifier.py](apps/agent-api/verifier.py) | **ตัวที่ใช้จริง** เป็น regex ไม่เรียก LLM (ดูหัวข้อ 7 ข้อ 1) ผลคือ `{supported, unsupported_claims, corrections}` |
| LLM client | [agent/llm.py](apps/agent-api/agent/llm.py) | จุดเดียวที่ทุก request ผ่าน มี `_merge_system`, `complete_structured`, `stream`, `LLMStats` |
| MCP client | [agent/mcp_client.py](apps/agent-api/agent/mcp_client.py) | `MCP_CLIENT_MODE=in_process` (ค่าเริ่มต้น import server มาเรียกตรง) หรือ `http` |
| Router | [agent/orchestrator.py](apps/agent-api/agent/orchestrator.py) | ทางเลือก Orchestrator-Workers สำหรับเปรียบเทียบ ไม่ใช่เส้นทางหลัก |

### 4.3 MCP server ([apps/mcp-server/](apps/mcp-server/))

- **Tools 19 ตัว:** tickets (6), network (5), logs (4), reports (3), notifications (1) ทั้งหมดอ่านอย่างเดียว ยกเว้น `generate_report` (เขียนไฟล์ในโฟลเดอร์รายงาน) และ `send_notification`
- **Resources:** `clock://now`, `schema://overview|postgres|neo4j|opensearch`, `files://index`, `files://read/{path}`
- **Prompts 5 ตัว:** แม่แบบการสืบสวนสำหรับ client ภายนอก (Claude Desktop/Cursor/Claude Code) เป็นข้อความ role `user` ที่แทนค่าพารามิเตอร์เท่านั้น agent ของเราไม่เรียกใช้
- **ที่ agent ใช้จริง:** `list_tools`, `call_tool`, และ resource `clock://now` เท่านั้น (`schema://*`, `files://*` และ prompts ไม่ถูกเรียกจาก agent)
- **Guardrails** ([security/guardrails.py](apps/mcp-server/security/guardrails.py)): `redact`/`redact_deep` (ทุก tool), `clamp_limit`, `safe_path`, `assert_allowlisted_script`, `refuse` + audit log ส่วน `assert_read_only` และ `cap_rows` มีเทสต์แต่**ยังไม่ถูกเรียกในโค้ด server** (ดูหัวข้อ 7)
- **เวลา** ([clock.py](apps/mcp-server/clock.py)): "ตอนนี้" = `@timestamp` ล่าสุดใน OpenSearch (หรือ `DEMO_NOW`) cache 300 วินาที tool รับเฉพาะ `last_1h|6h|24h|3d|7d|14d|30d|90d` ไม่รับวันที่จริง

### 4.4 ข้อมูล 3 แหล่ง

| ระบบ | เก็บ | ตอบคำถามแนว |
|---|---|---|
| PostgreSQL (+pgvector) | ticket, config อุปกรณ์, circuit, customer | ใครแจ้งอะไร / ตั้งค่าอย่างไร |
| Neo4j | topology, adjacency, interface | ต่อกับอะไร / มี upstream ร่วมไหม |
| OpenSearch | log, เอกสารที่ chunk+embed | อุปกรณ์รายงานอะไร / เคยแก้อย่างไร |

บัญชีที่ MCP ใช้คือ `mcp_reader` (อ่านอย่างเดียว) เท่านั้น ลำดับ seed คือ PostgreSQL → Neo4j → OpenSearch

### 4.5 โลกของข้อมูล (Scenario Bible)

เอกสารวิทยากร [data/scenarios.md](data/scenarios.md) เป็นแหล่งความจริงเดียวของ seed, ชุดคำถาม, เทสต์ และ eval (ห้ามให้ผู้เรียนอ่านก่อนทำโจทย์) มี 10 อุปกรณ์ใน 2 site (BKK 4, NBI 6)

| เหตุการณ์ | อุปกรณ์ | สอนเรื่อง |
|---|---|---|
| S1 interface flapping | `APE-NBI-03` (uplink ร่วมของ `LPE-NBI-11/12/13`) | หา root cause ข้ามระบบ ticket ไม่เอ่ยถึง APE |
| S2 เสื่อมเงียบ | `PE-BKK-02` | health score ต้องดูแนวโน้ม ไม่มี ticket |
| S3 config drift ข้าม site | `PE-NBI-04` ↔ `CR-BKK-02` | MTU 1500 กับ 9000, log บอกอาการ config บอกสาเหตุ |
| S4 planned maintenance | `APE-BKK-05` | log แรงแต่เป็นงานที่แจ้งไว้ ต้องเช็ก ticket maintenance |
| S5 ข้อมูลไม่มีอยู่จริง | เช่น `PE-CNX-99` | ต้องกล้าตอบว่าไม่พบ |

---

## 5. การตั้งค่า (`.env`)

- [.env.example](.env.example) = ตัวอย่างชุดเริ่มต้น (OpenRouter) ส่วน [.env.ex.nt](.env.ex.nt) = ตัวอย่างเซิร์ฟเวอร์ภายใน NT ไม่มี key ในทั้งสองไฟล์
- `.env` อยู่ใน `.gitignore` **ห้าม commit และห้ามแสดงค่า key ในผลลัพธ์หรือเอกสาร**
- เอกสารหลักสูตรบางหน้าอ้างเลขบรรทัดของ `.env.example` และไฟล์โค้ด (เช่น `.env.example:69`, `guardrails.py:79-90`) แก้ไฟล์เหล่านั้นแล้วต้องไล่แก้เลขบรรทัดในเอกสารด้วย

| กลุ่ม | ตัวแปรสำคัญ |
|---|---|
| LLM | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_MODEL_FAST`, `LLM_TIMEOUT_SECONDS`, `LLM_GUIDED_DECODING`, `LLM_ENABLE_THINKING` |
| Embedding | `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY` (ว่าง = ใช้ `LLM_API_KEY`), `EMBEDDING_MODEL`, `EMBEDDING_DIM=1024` |
| Rerank | `RERANK_BASE_URL`, `RERANK_MODEL`, `RERANK_TOP_K`, `RETRIEVE_TOP_K` |
| Agent | `AGENT_MAX_STEPS`, `AGENT_MAX_SAME_TOOL_CALLS`, `MEMORY_TOPIC_SHIFT_THRESHOLD`, `MEMORY_WINDOW_TURNS` |
| เวลา/ข้อมูล | `DEMO_NOW`, `SEED_RANDOM_SEED`, `SEED_DAYS_BACK` |
| เดโม | `DEMO_MODE` (`live`/`replay`), `PRESENTER_MODE`, `READ_ONLY` |

`LLM_ENABLE_THINKING=false` ส่ง `chat_template_kwargs.enable_thinking=false` ทุก request มีผลกับ vLLM/Qwen ส่วน OpenRouter ยังคงคืนช่อง `reasoning` ตามเดิม ตั้ง `true` ไว้สำหรับ OpenRouter และ `false` สำหรับ NT

---

## 6. กติกาสำหรับ agent ที่แก้ repo นี้

1. **เนื้อหาไทยของหลักสูตรใช้ภาษาทางการ** ไม่ใช้ภาษาพูด (ผู้ใช้ย้ำอย่างน้อย 3 ครั้ง)
2. **ไม่แก้เฉลยให้ผู้เรียนเห็นก่อนเวลา:** `solutions/` และ `data/scenarios.md` เป็นเนื้อหาวิทยากร ห้ามลิงก์จากเอกสารช่วงก่อนทำโจทย์
3. **ไม่ฝังกฎความปลอดภัยไว้ใน prompt อย่างเดียว** ถ้าเป็นกฎที่ต้องไม่ถูกฝ่าฝืน ให้เขียนเป็นโค้ดใน `guardrails.py` (ดู ADR-002)
4. **ไม่เพิ่ม `max_tokens`** ในการเรียก LLM โดยปริยาย โมเดลที่คิดก่อนตอบจะใช้งบหมดก่อนเริ่มตอบ ได้ content ว่าง (ส่งเฉพาะเมื่อมีเหตุผลจริง ผ่านพารามิเตอร์ `max_tokens` ของ `llm.complete`)
5. **ไม่ใช้ system message หลายก้อนโดยหวังว่าจะส่งถึงโมเดลตามเดิม** ทุก request ถูกรวมเป็นก้อนเดียวใน `_merge_system` (ดู ADR-006)
6. **เพิ่ม tool ใหม่ต้องแก้มากกว่าหนึ่งที่** ดู [INSTRUCTIONS/day3/05-summary-add-mcp-tool.md](INSTRUCTIONS/day3/05-summary-add-mcp-tool.md) และเขียน docstring แบบ "ใช้เมื่อไร / ห้ามใช้เมื่อไร" (ADR-011) ตั้ง annotation ให้ตรงพฤติกรรมจริง
7. **ไฟล์ shell/SQL/template ต้องเป็น LF** (ADR-012)
8. **เปลี่ยน `RANGES` ใน `clock.py` ต้องอัปเดตให้ตรงกับ prompt ของ ReAct (ข้อ 3) และรายการ `accepted_ranges`** ซึ่งมาจาก `clock.coverage()` อัตโนมัติ
9. เมื่อทำงานใน git worktree ให้แก้ไฟล์ใน worktree นั้นเท่านั้น และ commit เมื่อผู้ใช้สั่งเท่านั้น

---

## 7. ปัญหาและข้อสังเกตที่ทราบแล้ว

ตรวจพบจากการอ่านโค้ดในรอบนี้ (ยังไม่ได้แก้ เว้นแต่ระบุ)

1. **Grounding สองชุด ใช้จริงชุดเดียว:** `main.py` เรียก `verifier.verify` (regex, ไม่เรียก LLM) ส่วน [agent/grounding.py](apps/agent-api/agent/grounding.py) (ตัวตรวจแบบ LLM พร้อม system prompt) ถูก import แต่**ไม่ถูกเรียก** และ `verifier-v0.py` เป็นฉบับเก่า การอธิบายก่อนหน้านี้ที่นับ prompt ของ `grounding.py` เป็นส่วนหนึ่งของ pipeline จริงจึงไม่ถูกต้อง
2. `guardrails.assert_read_only` และ `cap_rows` ไม่มีผู้เรียกในโค้ด server ชั้นป้องกันที่ทำงานจริงคือ role `mcp_reader`, `redact_deep`, `clamp_limit` และ allowlist
3. `main.py` มี `from agent import clock_probe` ใน `/health` แต่ไม่มีไฟล์นี้ (เข้า `except ImportError` ทุกครั้ง) ลบได้
4. docstring ของ `get_upstream_devices` เหลือบรรทัดเดียว ขณะที่ tool อื่นมีคำอธิบายครบ และตาราง `routing_questions_to_stores` ใน `schema://overview` ไม่มีคำถามประเภท "ลูกค้ากี่รายได้รับผลกระทบ" (`get_circuits_by_device`) ซึ่งสัมพันธ์กับที่ agent ตอบคำถามผลกระทบตกหล่นอุปกรณ์ downstream
5. `RANGES` ไม่มีช่วงแบบเลื่อน (เช่น 7–14 วันก่อน) จึงตอบ "เมื่อสองสัปดาห์ก่อน" ได้ไม่แม่น
6. `send_notification` ตั้ง `openWorldHint: False` เพราะเวิร์กช็อปส่งผ่าน MailHog ในเครื่อง ถ้าเปลี่ยนไปส่งออกนอกองค์กรต้องเปลี่ยนเป็น `True`
7. `schema://overview` ระบุ `device_count: 10` เขียนตายตัว ถ้า seed เปลี่ยนจำนวนอุปกรณ์ต้องแก้ด้วย
8. agent ไม่อ่าน `schema://overview` แม้ `INSTRUCTIONS` ของ server แนะนำให้อ่านก่อน query แรก (มีผลเฉพาะ client ภายนอก)
9. พบระหว่างทดสอบ: `qwen/qwen3-30b-a3b` ผ่าน OpenRouter ตอบ root cause ของ S1 ผิดบางครั้งและอ้าง ticket คลาดเคลื่อน, embedding ผ่าน OpenRouter ช้าเป็นช่วงๆ (timeout 20 วินาทีแล้วถอยไปใช้ keyword), พารามิเตอร์ปิดโหมดคิดไม่มีผลกับ OpenRouter
10. image เดโมไม่มี `transformers` ตัวเลข context ใน UI จึงเป็นค่าประมาณ
11. ปัญหา CRLF บนเครื่อง Windows: แก้แล้วในสคริปต์และเอกสาร แต่ยังไม่ได้ยืนยันบนเครื่องจริง

---

## 8. ADR (Architecture Decision Records)

แต่ละการตัดสินใจแยกเป็นไฟล์ใน [docs/adr/](docs/adr/README.md) (รูปแบบ: บริบท → ตัดสินใจ → ผลที่ตามมา) สถานะทั้งหมดคือ **Accepted** และเป็นบันทึกย้อนหลังจากโค้ดปัจจุบัน

| ADR | หัวข้อ |
|---|---|
| [001](docs/adr/0001-react-loop-instead-of-planner-executor.md) | ReAct loop แทน planner/executor |
| [002](docs/adr/0002-code-enforced-layered-guardrails.md) | Guardrail บังคับด้วยโค้ดหลายชั้น |
| [003](docs/adr/0003-data-derived-now-and-relative-ranges.md) | "ตอนนี้" มาจากข้อมูล และใช้ช่วงเวลาสัมพัทธ์เท่านั้น |
| [004](docs/adr/0004-single-mcp-server-in-process-default.md) | เข้าถึงข้อมูลผ่าน MCP server เดียว (in-process เป็นค่าเริ่มต้น) |
| [005](docs/adr/0005-three-layer-structured-output.md) | Structured output 3 ชั้น |
| [006](docs/adr/0006-swappable-openai-compatible-gateway.md) | Gateway แบบ OpenAI-compatible ที่สลับได้ |
| [007](docs/adr/0007-two-layer-intent-gate.md) | Intent Gate สองชั้น |
| [008](docs/adr/0008-topic-shift-memory-with-summaries.md) | Memory แบบตรวจการเปลี่ยนหัวข้อและสรุป |
| [009](docs/adr/0009-regex-grounding-instead-of-llm-judge.md) | Grounding แบบ regex แทน LLM-judge |
| [010](docs/adr/0010-scenario-first-deterministic-dataset.md) | ชุดข้อมูลแบบ scenario-first และ seed แบบกำหนดผลได้ |
| [011](docs/adr/0011-tool-docstring-as-selection-contract.md) | docstring ของ tool คือสัญญาการเลือก tool |
| [012](docs/adr/0012-docker-and-database-layout.md) | โครงสร้าง Docker และฐานข้อมูล |
| [013](docs/adr/0013-demo-app-separate-from-learner-ui.md) | แอปเดโมแยกจาก UI ของผู้เรียน |
| [014](docs/adr/0014-redact-secrets-at-tool-output.md) | ปิดบังความลับที่ขอบเขตขาออกของ tool |

## 9. เอกสารอ้างอิงเพิ่มเติม

| เรื่อง | ที่ |
|---|---|
| แผนที่หลักสูตรและตารางเวลา | [README.md](README.md) |
| ภาพรวมสถาปัตยกรรมและ model stack | [README2.md](README2.md) |
| Tool, Resource, Prompt, annotation ของ MCP server | [apps/mcp-server/TOOLS.md](apps/mcp-server/TOOLS.md) |
| เพิ่ม tool ใหม่ให้ agent จริง | [INSTRUCTIONS/day3/05-summary-add-mcp-tool.md](INSTRUCTIONS/day3/05-summary-add-mcp-tool.md) |
| แก้ Intent / Memory ใน app จริง | [INSTRUCTIONS/day2/07-summary-intent-memory-in-app.md](INSTRUCTIONS/day2/07-summary-intent-memory-in-app.md) |
| แก้ JSON template ของ agent | [INSTRUCTIONS/day1/08-summary-json-template-in-app.md](INSTRUCTIONS/day1/08-summary-json-template-in-app.md) |
| แก้ปัญหาที่พบบ่อย | [INSTRUCTIONS/reference/troubleshooting.md](INSTRUCTIONS/reference/troubleshooting.md) |
| ตัวจำลอง flow ของ agent (ไฟล์ HTML เดี่ยว) | [INSTRUCTIONS/day1/flow-simulator.html](INSTRUCTIONS/day1/flow-simulator.html) |
| การวัดคุณภาพ L0–L7 | [eval/README.md](eval/README.md) |
