# Module 4 · ReAct Pattern

**09:00 – 10:00** (60 นาที) · เป้าหมาย: เข้าใจวงจร Thought → Action → Observation ของ ReAct และเหตุผลที่ระบบวินิจฉัยเครือข่ายต้องใช้วิธีนี้แทนการตอบทีเดียวจบ (one-shot)

โมดูลนี้เป็นเนื้อหาเชิงแนวคิดล้วน **ไม่มีการลงมือเขียนโค้ด** — การเขียน ReAct loop เองเริ่มที่ [Module 5](03-module5-react-loop.md) หลังจาก [Module 7 · Intent Gate](02-module7-intent-gate.md)

---

## 1. ทำไมการตอบทีเดียวจบถึงใช้ไม่ได้กับงานวินิจฉัยเครือข่าย

ลองพิจารณาคำถามจริงที่ Agent ของ NOC ต้องตอบ: *"ลูกค้าหลายรายแจ้งว่าอินเทอร์เน็ตหลุดเป็นช่วงๆ สาเหตุคืออะไร"*

แนวทาง **one-shot** (ยัด context ทั้งหมดให้โมเดลในครั้งเดียวแล้วขอคำตอบ) และแนวทาง **plan-then-execute** (ให้โมเดลวางแผนทุกขั้นตอนล่วงหน้าก่อนเริ่มทำ) มีจุดอ่อนร่วมกันคือ **ต้องรู้ล่วงหน้าว่าจะเจออะไร** ซึ่งเป็นไปไม่ได้ในทางปฏิบัติ:

- ไม่รู้ล่วงหน้าว่าจะมี ticket กี่ใบ จนกว่าจะ query จริง
- ไม่รู้ล่วงหน้าว่า ticket เหล่านั้นอยู่บนอุปกรณ์ตัวไหนบ้าง จนกว่าจะเห็นผลลัพธ์
- ไม่รู้ล่วงหน้าว่าอุปกรณ์เหล่านั้นมี upstream ร่วมกันหรือไม่ จนกว่าจะ query กราฟ topology
- แผนที่วางไว้ล่วงหน้าจะ "ผิด" ทันทีที่ผลลัพธ์จริงต่างจากที่คาดไว้ — เช่น ticket ว่างเปล่า หรือพบอุปกรณ์ที่ไม่มีใครคาดถึง

`apps/agent-api/agent/react.py:1-9` อธิบายหลักการนี้ตรงไปตรงมา: ไม่มีการสร้าง plan object ล่วงหน้า ในทุกรอบโมเดลเห็นเป้าหมายและทุก observation ที่มีอยู่ ณ ขณะนั้น แล้วตัดสินใจ "ก้าวถัดไปหนึ่งก้าว" เท่านั้น สิ่งที่ต้องแลกคือความสามารถตรวจสอบแผนล่วงหน้า (inspectability) ที่ plan-then-execute ให้ได้ แต่สิ่งที่ได้กลับมาคือความสามารถปรับตัวกลางทาง

---

## 2. วงจร ReAct: Thought → Action → Observation

```mermaid
flowchart LR
    T["Thought<br/>รู้อะไรแล้วบ้าง จะทำอะไรต่อ"] --> A{"Action"}
    A -->|"เลือกเครื่องมือ"| C["เรียก Tool จริง"]
    A -->|"tool = null"| E(["ออกจาก loop<br/>พร้อมสังเคราะห์คำตอบ"])
    C --> O["Observation<br/>ผลลัพธ์ หรือ ERROR"]
    O -->|"กลับเข้า scratchpad"| T

    style E fill:#e0ffe0,stroke:#0a0
```

องค์ประกอบทั้งสามในโค้ดจริงของ `solutions/day2/workshop2_agent.py`:

| ส่วน | คืออะไร | อยู่ตรงไหนในโค้ด |
|---|---|---|
| **Thought** | เหตุผลสั้นๆ หนึ่งประโยคว่ารู้อะไรแล้วและจะทำอะไรต่อ | field `thought` ของ `ReactDecision` — `solutions/day2/workshop2_agent.py:224` |
| **Action** | ชื่อเครื่องมือที่จะเรียก + argument หรือ `null` ถ้าพอตอบแล้ว | field `tool`/`arguments` ของ `ReactDecision` — `solutions/day2/workshop2_agent.py:225-228`, เรียกจริงใน `call_one_tool()` — `solutions/day2/workshop2_agent.py:351-362` |
| **Observation** | ผลลัพธ์ของ tool (สำเร็จ) หรือข้อความ error (ล้มเหลว) ถูกใส่กลับเข้าไปใน scratchpad เป็น turn ถัดไป | `append_turn()` — `solutions/day2/workshop2_agent.py:365-381` |

จุดที่มักเข้าใจผิด: **ไม่มีขั้นตอน "ซ่อมแซม argument" แยกต่างหาก** เมื่อ tool call ล้มเหลว ข้อความ error จะกลายเป็น observation ของรอบถัดไปโดยตรง (`ERROR: ...` ตามรูปแบบใน `append_turn()` บรรทัด 379-380) แล้วโมเดลจะแก้ไข argument เองในรอบคิดถัดไป เหมือนกับการปรับตัวจาก observation ประเภทอื่นทุกประการ — ตามที่ระบุไว้ใน docstring ของไฟล์เดียวกัน (`solutions/day2/workshop2_agent.py:15-17`)

วงจรนี้ถูกจำกัดด้วยเพดานสามชั้นเสมอ (รายละเอียดอยู่ใน Module 5): จำนวนขั้นตอนรวม (`MAX_STEPS`), การเรียกซ้ำด้วย argument เดิม, และจำนวนครั้งสูงสุดต่อหนึ่งเครื่องมือ (`MAX_SAME_TOOL`) — ดู `solutions/day2/workshop2_agent.py:56-57` และคลาส `LoopGuard` ที่ `solutions/day2/workshop2_agent.py:316-344`

---

## 3. เปรียบเทียบกับการตอบทีเดียวจบ (One-Shot / Plan-then-Execute)

| มิติ | One-Shot | Plan-then-Execute | ReAct |
|---|---|---|---|
| ปรับตัวเมื่อผลลัพธ์ไม่ตรงคาด | ทำไม่ได้ — คำตอบเดียวจบ | ทำไม่ได้กลางทาง ต้องวางแผนใหม่ทั้งหมด | ปรับได้ทุกรอบ เพราะตัดสินใจหลังเห็น observation แล้ว |
| ตรวจสอบก่อนรันจริง (inspectability) | ไม่มีอะไรให้ตรวจ | ตรวจ plan ทั้งหมดได้ก่อนเริ่ม | ตรวจได้ทีละก้าวเท่านั้น ไม่เห็นล่วงหน้า |
| ความเสี่ยง loop ไม่จบ | ไม่มี (ไม่มี loop) | ต่ำ (จำนวนขั้นตอนถูกกำหนดไว้ในแผน) | มีจริง — ต้องมี `LoopGuard` ป้องกัน |
| เหมาะกับคำถามที่ต้องเชื่อมหลายแหล่งข้อมูล | ไม่เหมาะ | พอใช้ได้ถ้ารู้ลำดับล่วงหน้า | เหมาะที่สุด เพราะไม่รู้ล่วงหน้าว่าต้องข้ามไปแหล่งไหนต่อ |
| ต้นทุน token ต่อคำถาม | ต่ำสุด | ปานกลาง | สูงสุด — เรียก LLM ทุกรอบของ loop |

**ข้อสรุป**: ไม่มีรูปแบบใดชนะทุกกรณี ระบบของ workshop นี้เลือก ReAct เพราะโจทย์วินิจฉัยเครือข่าย (เช่นเหตุการณ์ interface flapping ใน `data/scenarios.md`) ต้องอาศัยการค้นพบสาเหตุร่วมที่ไม่ปรากฏใน ticket ตั้งแต่ต้น — รู้ได้ก็ต่อเมื่อเห็นผลลัพธ์จริงจาก Neo4j เสียก่อน

---

## 4. อ่าน ReAct Trace ตัวอย่าง

พิจารณาเป้าหมายเดียวกับที่ใช้เป็นตัวอย่างในไฟล์เฉลย (`solutions/day2/workshop2_agent.py:472-473`, ตรงกับตัวอย่างการเรียกใช้ใน docstring บรรทัด 4-5):

```
uv run python solutions/day2/workshop2_agent.py "หา ticket ที่ยังไม่ปิดของสัปดาห์นี้ ทำรายงานสรุป แล้วส่งเมลให้ทีม NOC"
```

Trace ด้านล่างคือ**ผลลัพธ์จริง** จากการรันคำสั่งข้างบนตรงๆ (ไม่ใช่ค่าสมมติ) ตามรูปแบบของฟังก์ชัน `run()` (`solutions/day2/workshop2_agent.py:424-469`):

```
====================================================================
  เป้าหมาย: หา ticket ที่ยังไม่ปิดของสัปดาห์นี้ ทำรายงานสรุป แล้วส่งเมลให้ทีม NOC
====================================================================

  [ReAct loop]
    1. คิด: เริ่มต้นด้วยการค้นหา ticket ที่ยังไม่ปิดในช่วง 7 วันที่ผ่านมา
       เรียก search_tickets({"status": "open", "days": 7, "limit": 20})
        -> สำเร็จ 128 ms
    2. คิด: มี ticket ที่ยังไม่ปิด 3 รายการ ต่อไปจะสรุปข้อมูลเหล่านี้เป็นรายงาน
       เรียก export_report({"title": "Ticket ที่ยังไม่ปิดของสัปดาห์นี้", "rows": [{"ticket_id": ")
        -> สำเร็จ 1 ms
    3. คิด: สรุปข้อมูลเป็นรายงานแล้ว ตอนนี้จะส่งอีเมลให้ทีม NOC
       เรียก send_notification({"subject": "Ticket ที่ยังไม่ปิดของสัปดาห์นี้", "body": "รายงาน ticket)
        -> สำเร็จ 168 ms
    4. คิด: ดำเนินการเสร็จสิ้น ได้ส่งอีเมลรายงานไปยังทีม NOC แล้ว (เครื่องมือ 'null' ไม่มีจริง)

  [สรุป]

มี ticket ที่ยังไม่ปิด 3 รายการในสัปดาห์นี้ ดังนี้:
1. TK-25-00005 (NBI, LPE-NBI-12) - "เน็ตหลุดซ้ำ เคสเดิมที่เคยแจ้งไว้" (เปิดเมื่อ 2026-09-24)
2. TK-25-00018 (BKK, APE-BKK-05) - "วงจรล่ม ใช้งานไม่ได้ทั้งสาขา" (เปิดเมื่อ 2026-09-24)
3. TK-25-00011 (NBI, LPE-NBI-12) - "โหลดไฟล์ช้ากว่าปกติมาก" (เปิดเมื่อ 2026-09-23)

รายงานสรุปถูกสร้างในรูปแบบ markdown ที่ path: data/reports/report-20260930-102613.md และส่งไปยังทีม NOC แล้วที่ email: noc-team@example.com (ตรวจสอบได้ที่ http://localhost:8025)
(PostgreSQL: ticket TK-25-00005, TK-25-00018, TK-25-00011)

  ------------------------------------------------------------------
  3/3 เครื่องมือสำเร็จ · ใช้เวลารวม 16.6 วินาที
  ตรวจอีเมลที่ http://localhost:8025
```

**โค้ดส่วนที่ทำให้ "Action" กลายเป็นการเรียกจริง**: ทุกบรรทัด `เรียก search_tickets({...})` ใน trace ข้างบนไม่ได้พิมพ์ขึ้นมาเฉยๆ แต่มาจากโค้ดสองส่วนนี้ต่อกัน — จุดที่แปลงชื่อ tool (สตริงที่โมเดลตอบมา) ให้กลายเป็นฟังก์ชัน Python ตัวจริงที่ถูกเรียกด้วย argument จริง:

```python
# solutions/day2/workshop2_agent.py:210-216
TOOLS = {
    "search_tickets": search_tickets,
    "get_upstream_devices": get_upstream_devices,
    "count_log_events": count_log_events,
    "export_report": export_report,
    "send_notification": send_notification,
}
```

```python
# solutions/day2/workshop2_agent.py:351-362
async def call_one_tool(tool: str, arguments: dict) -> dict:
    started = time.time()
    try:
        # Tools are synchronous; run them off the event loop so the process
        # is not blocked while a DB or HTTP call is in flight.
        result = await asyncio.to_thread(TOOLS[tool], **arguments)
        elapsed = int((time.time() - started) * 1000)
        print(f"        -> สำเร็จ {elapsed} ms")
        return {"ok": True, "tool": tool, "result": result}
    except Exception as exc:  # noqa: BLE001
        print(f"        -> ล้มเหลว: {type(exc).__name__}: {exc}")
        return {"ok": False, "tool": tool, "error": f"{type(exc).__name__}: {exc}"}
```

อ่านสองส่วนนี้ต่อกัน: `decision.tool` ที่โมเดลตอบมาเป็นแค่สตริง เช่น `"search_tickets"` — `TOOLS[tool]` คือขั้นตอนที่เอาสตริงนั้นไป**หาฟังก์ชันจริง**จาก dict (บรรทัดที่ 1 ของ trace ข้างบนจึงเรียก `TOOLS["search_tickets"]` ซึ่งก็คือฟังก์ชัน `search_tickets` ที่นิยามไว้ด้านบนไฟล์) แล้ว `**arguments` คือการแกะ dict argument ที่โมเดลส่งมา (`{"status": "open", "days": 7, "limit": 20}`) ออกมาเป็น keyword argument ตรงๆ เท่ากับเรียก `search_tickets(status="open", days=7, limit=20)` — และเนื่องจาก tool ทุกตัวเขียนเป็นฟังก์ชัน synchronous ธรรมดา (ใช้ `psycopg`/`OpenSearch` client แบบ blocking) จึงต้องห่อด้วย `asyncio.to_thread(...)` เพื่อไม่ให้ค้าง event loop ระหว่างรอ DB ตอบ ส่วน `try/except` ทำให้ tool ที่ล้มเหลวไม่ทำให้ทั้ง process ตาย แต่กลายเป็นข้อความ error ที่ถูกส่งกลับเข้า scratchpad เป็น observation ของรอบถัดไปแทน (ตามที่อธิบายไว้ในหัวข้อ 2 ด้านบน) — และเพราะชื่อ tool ถูกตรวจสอบว่ามีอยู่จริงใน `TOOLS` ไปแล้วตั้งแต่ `decide_next_step()` (`solutions/day2/workshop2_agent.py:304-308`) โค้ดส่วนนี้จึงมั่นใจได้ว่า `TOOLS[tool]` จะไม่ throw `KeyError` เด็ดขาด

**จุดที่ควรสังเกตในการอ่าน trace นี้**

1. รอบที่ 4 คือจุดที่โมเดลตั้ง `tool = null` — ออกจาก loop ทันทีตามเงื่อนไขที่ `solutions/day2/workshop2_agent.py:437-438` **แต่สังเกตข้อความในวงเล็บท้ายคิดข้อ 4** (`เครื่องมือ 'null' ไม่มีจริง`) — นี่คือของจริงที่รันได้ตรงกับที่เตือนไว้ใน [Module 5 หัวข้อ 1.3](03-module5-react-loop.md): โมเดลตอบสตริงตัวอักษร `"null"` แทนที่จะเป็นค่า JSON `null` จริง ทำให้ตัวตรวจชื่อเครื่องมือ (`solutions/day2/workshop2_agent.py:304-308`) มองว่า `"null"` เป็นชื่อเครื่องมือที่ไม่มีจริงและปฏิเสธไป แต่ผลลัพธ์สุดท้ายก็ยังถูกต้องเพราะเงื่อนไข stop sequence ของฟังก์ชันนี้ตรวจแค่ `decision.tool is None` และค่าที่ถูกปฏิเสธถูก reset เป็น `None` ไปแล้ว
2. ลำดับ `export_report` ก่อน `send_notification` **ไม่ใช่เรื่องบังเอิญ** แต่เป็นกติกาที่บังคับไว้ในพร้อมต์ (`REACT_PROMPT` ข้อ 3 — `solutions/day2/workshop2_agent.py:268-269`): "ถ้าผู้ใช้ขอให้ส่งผลให้ทีม ต้องเรียก `export_report` ก่อน `send_notification` เสมอ" — แสดงว่าลำดับการกระทำใน ReAct ไม่ได้เกิดขึ้นเองอัตโนมัติ แต่ต้องระบุไว้ในพร้อมต์อย่างชัดเจน
3. แต่ละ Observation (ผลลัพธ์ของแต่ละขั้น) กลายเป็นข้อมูลตั้งต้นของ **การสังเคราะห์คำตอบ** (`synthesize()` — `solutions/day2/workshop2_agent.py:405-417`) ซึ่งบังคับให้ต้องอ้างอิงแหล่งที่มาจริงของทุกข้อสรุป (`SYNTH_PROMPT` — `solutions/day2/workshop2_agent.py:388-402`) — ป้องกันไม่ให้โมเดลเดาหมายเลข ticket หรืออุปกรณ์ที่ไม่มีในหลักฐาน สังเกตว่าคำตอบจริงข้างบนอ้างอิงหมายเลข ticket จริง (`TK-25-00005`, `TK-25-00018`, `TK-25-00011`) ที่ได้จาก PostgreSQL ตรงๆ ไม่ได้เดาขึ้นมาเอง
4. ไฟล์รายงานและอีเมลข้างบนเป็นของจริงที่ถูกสร้างขึ้นจากการรันครั้งนี้ (`data/reports/report-20260930-102613.md` และอีเมลใน MailHog ที่ http://localhost:8025) — ลองรันคำสั่งข้างบนซ้ำเองได้ ผลลัพธ์ตัวเลข ticket และเวลาที่ใช้อาจต่างไปเล็กน้อยตามข้อมูลจริงในฐานข้อมูล ณ ขณะนั้น

**ถ้าลองรันแล้ว "ไม่เจออะไร"** (เช่น `search_tickets`/`count_log_events` คืนค่าว่างเปล่า ทั้งที่ควรมีข้อมูล): เครื่องมือทั้งสองกรองด้วยช่วงเวลาสัมพัทธ์ (`opened_at >= now - days`, `@timestamp: now-{days}d`) ถ้าข้อมูลถูก seed ไว้นานแล้ว timestamp จะ "หลุดหน้าต่าง" ที่ query มองหาไป ให้ refresh timestamp ของ log ใน OpenSearch ให้ขยับมาอยู่แถว "ตอนนี้" ด้วยคำสั่งนี้ (เทียบเท่า `make load-logs SHIFT=now` แต่เรียก docker compose ตรงๆ โดยไม่ผ่าน make):

```bash
docker compose -f docker/docker-compose.yml --env-file .env run --rm loader python load_logs.py --shift now
```

คำสั่งนี้จะขยับ timestamp ของทุกบรรทัด log ที่โหลดไว้แล้วให้บรรทัดล่าสุดตรงกับเวลาปัจจุบัน โดยคงระยะห่างสัมพัทธ์ระหว่างเหตุการณ์ไว้เหมือนเดิม (ดูเหตุผลใน docstring ของ `docker/loader/load_logs.py:2-12`)

---

## ต่อไป

→ [Module 7: Intent Gate](02-module7-intent-gate.md) — ก่อนลงมือเขียน loop เต็มรูปแบบ ต้องรู้ก่อนว่าคำถามแบบไหนไม่ควรเข้า loop เลยด้วยซ้ำ
