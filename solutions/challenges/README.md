# เฉลยโจทย์ประจำวัน

> ⚠️ อ่านก่อนลอง = เสียโอกาสเรียนรู้ · ดูวิธีใช้ที่ [../README.md](../README.md)

| โจทย์ | ไฟล์ | คำสั่ง |
|---|---|---|
| [1 · Thai Token Audit](../../INSTRUCTIONS/day1/04-challenge1-thai-token-audit.md) | `challenge1_token_audit.py` | `uv run solutions/challenges/challenge1_token_audit.py` |
| [2 · Schema Under Pressure](../../INSTRUCTIONS/day1/07-challenge2-schema-under-pressure.md) | `challenge2_before.py` (baseline, ขั้นที่ 1 ของโจทย์) + `challenge2_robust_extractor.py` (เฉลย) | `uv run solutions/challenges/challenge2_before.py` แล้วค่อย `uv run solutions/challenges/challenge2_robust_extractor.py` |
| [3 · Tool Description Battle](../../INSTRUCTIONS/day2/03-challenge3-tool-description-battle.md) | `challenge3_descriptions.json` | ดูวิธีใช้ด้านล่าง |
| [4 · Topic Shift Survival](../../INSTRUCTIONS/day2/08-challenge4-topic-shift-survival.md) | `challenge4_topic_shift.py` | `uv run solutions/challenges/challenge4_topic_shift.py` |
| 5 · Guardrail Red-team | `tests/test_guardrails.py` | `uv run pytest tests/test_guardrails.py` |
| 6 · Cross-Service Diagnosis | `make eval` | ดู `eval/results/latest.json` |

---

## โจทย์ที่ 1 — สิ่งที่ควรได้จากตัวเลข

สคริปต์ตอบ 3 คำถาม:

1. **ภาษาไทยแพงกว่าอังกฤษกี่เท่า** ที่จำนวนอักขระเท่ากัน
2. **tiktoken ผิดกี่เปอร์เซ็นต์** เมื่อเอามาใช้กับ Gemma
3. **ต้นทุนจริงเมื่อขึ้น production** 2,600 อุปกรณ์

ข้อ 2 คือข้อสรุปที่สำคัญที่สุด — ถ้าใช้ตัวเลขจาก tokenizer ผิดรุ่นไปวางแผนงบประมาณหรือกำหนดขนาด chunk จะผิดตั้งแต่ต้นโดยไม่มีอะไรเตือน

สคริปต์ใช้ `setseed(0.42)` เพื่อให้สุ่มตัวอย่างได้ผลเดิมทุกครั้ง — ตัวเลขในรายงานจึงสร้างซ้ำได้

---

## โจทย์ที่ 2 — 4 การป้องกัน

`challenge2_before.py` คือขั้นที่ 1 ของโจทย์ทำสำเร็จรูปไว้ให้: รัน `StructuredExtractor` ดิบๆ จาก Workshop 1 (ยังไม่แก้อะไร) กับทั้ง 25 ใบ เพื่อเห็น **"ก่อนแก้" พังตรงไหนบ้าง** ก่อนไปดู `challenge2_robust_extractor.py` ที่เป็น "หลังแก้" — รันสองไฟล์นี้เทียบ list "ยังไม่ผ่าน" กัน จะเห็นชัดว่า 4 การป้องกันด้านล่างแก้อะไรไปบ้างจริงๆ ไม่ใช่แค่คำอธิบายลอยๆ

> **ข้อสังเกตจากการรัน `challenge2_before.py` จริง**: แม้แต่โค้ดดิบของ Workshop 1 ก็ยัง reject `"ALL"` เป็นชื่ออุปกรณ์ได้ (เพราะ `device_must_match_site` validator เช็คกับ `VALID_DEVICES` อยู่แล้ว) แต่พอ retry ครบ 3 ครั้งแล้วยังไม่ผ่าน มันตกไปที่ fallback ซึ่งเขียน `summary_th=text[:180]` — copy ข้อความดิบของผู้โจมตีใส่ output ตรงๆ นี่คือช่องโหว่ที่ซ่อนอยู่ใน fallback path เอง

| ป้องกัน | แก้ปัญหาของ | วิธี |
|---|---|---|
| ตัดข้อความยาว | ใบที่ 2 (40 ข้อความ) | เก็บ**หัวและท้าย** ทิ้งตรงกลาง |
| Delimiter + system prompt | ใบที่ 4 (injection) — ชั้นแรก | แยก "คำสั่ง" ออกจาก "ข้อมูล" ให้ชัด |
| `confidence` ต่ำเมื่อข้อมูลน้อย | ใบที่ 1, 3 | บังคับใน field description |
| Circuit breaker | ปัญหาเชิงระบบ | ล้มเหลวติดกัน 5 ครั้ง = หยุด |

**ทำไมตัดตรงกลาง ไม่ใช่ตัดท้าย**: ตรงกลางคือจุดที่โมเดลใช้ข้อมูลได้แย่ที่สุดอยู่แล้ว (Module 2) และข้อความแรกๆ บอกอาการ ส่วนข้อความท้ายๆ บอกผลการแก้ไข — ซึ่งเป็นสองสิ่งที่กำลังสกัดพอดี

### เรื่องเดียวที่แก้ไปหลังพบว่ายังไม่ผ่านจริง — injection ต้อง "ป้องกัน" ไม่ใช่แค่ "ตรวจจับ"

`challenge2_before.py` เผยให้เห็น**บั๊กจริง** ไม่ใช่แค่ข้อจำกัดที่ตั้งใจ: โค้ดตรวจจับ injection ได้ (`injection_detected=True`) แต่โค้ดที่ลด confidence อยู่หลังเงื่อนไข `if result.ok and result.data:` — และ `NOISY-04` validate ไม่ผ่านครบ 3 รอบเสมอ (`result.ok=False`) ทำให้โค้ดป้องกันทั้งหมด**ไม่เคยถูกรันเลยสักครั้ง** ผลคือ `before` กับ `after` (เวอร์ชันเดิม) พังเหมือนกันเป๊ะ

**สิ่งที่แก้จริงในไฟล์นี้ ณ ตอนนี้**:
1. `if result.ok and result.data:` → `if result.data:` — โค้ดป้องกันต้องรันไม่ว่า extraction จะสำเร็จหรือ fallback ก็ตาม
2. เพิ่ม `_neutralize()` — **ตัดบรรทัดที่มี marker ออกจากข้อความก่อนส่งเข้า LLM เลย** (ไม่ใช่แค่ log ไว้เฉยๆ) โมเดลไม่มีทางเอ่ยถึงคำสั่งที่มันไม่เคยเห็น — แก้ปัญหา `"ALL"` ที่เป็นค่าที่ attacker เลือกเองแบบไม่มีทางระบุไว้ล่วงหน้าในลิสต์ marker ได้ด้วย เพราะตัดทั้งบรรทัดทิ้ง ไม่ใช่ตัดแค่คำที่ match
3. เพิ่ม `_redact_leaks()` — เป็นด่านสุดท้าย กรองคำใน marker list ออกจาก `summary_th`/`customer_impact` **หลัง**ได้ผลลัพธ์แล้ว เผื่อโมเดล paraphrase มาแบบที่ `_neutralize()` ป้องกันไม่ทัน

ผลหลังแก้: **25/25** (จากเดิม 24/25 ทั้ง before และ after) และ `NOISY-04` ผ่านตั้งแต่รอบแรกโดยไม่ต้อง retry เลย — ตรงกับหลักการของ Module 8 ที่ว่า **"detection ไม่ใช่ prevention" ต้องมีโค้ดที่บังคับจริง ไม่ใช่แค่ log แล้วหวังว่าจะพอ**

---

## โจทย์ที่ 3 — วิธีใช้เฉลย

1. เปิด `challenge3_descriptions.json`
2. คัดลอกส่วน `descriptions_under_test` ไปแทนที่ใน `data/challenge_fixtures/tool_selection_cases.json`
3. รัน `uv run pytest tests/test_tool_selection.py -s`

คะแนนควรขึ้นจาก ~5/12 เป็น 11-12/12

**อ่านส่วน `why_it_works` และ `cases_still_hard` ด้วย** — ข้อ TS-12 ยังพลาดได้แม้ description ดีแล้ว เพราะเป็นสัญญาณว่า tool ออกแบบทับซ้อนกันตั้งแต่แรก ซึ่งเป็นบทเรียนที่ลึกกว่าการแก้ prose

---

## โจทย์ที่ 4 — กราฟคือคำตอบ

สคริปต์พิมพ์กราฟแท่งของ `context_tokens` ทั้ง 10 turn และตรวจ 3 จุด:

| turn | ต้องเกิดอะไร |
|---|---|
| **5** | นอกขอบเขต · `tool_calls == 0` · **context ไม่ถูกล้าง** |
| **6** | เปลี่ยนเรื่อง · context **ลดลงอย่างน้อย 40%** |
| **9** | ย้อนเรื่องเดิม · ตอบได้จากสรุป · เรียก tool ไม่เกิน 1 ครั้ง |

ถ้ากราฟเป็นเส้นที่โตขึ้นตลอด แปลว่ากลไกความจำยังไม่ทำงาน ไม่ว่าคำตอบแต่ละ turn จะดูดีแค่ไหน

ผลถูกบันทึกไว้ที่ `challenge4_result.json` เอาไปวาดกราฟต่อได้

---

## โจทย์ที่ 5 และ 6 — ทำไมไม่มีไฟล์เฉลย

**โจทย์ที่ 5** เป็นการทดลองเชิงปฏิบัติ (แดง/น้ำเงิน) ที่ไม่มี "คำตอบเดียว" — สิ่งที่ใกล้เคียงเฉลยที่สุดคือ `tests/test_guardrails.py` ซึ่งกำหนดว่าอะไรบ้างที่ต้องถูกบล็อก

> การทดลองที่สำคัญที่สุดของโจทย์นี้คือ **ปิด guardrail ทีละชั้นแล้วทดสอบซ้ำ**
> คำตอบที่ต้องค้นพบเอง: ปิดชั้นบนได้ ระบบยังปลอดภัย แต่พอเปลี่ยนบัญชีฐานข้อมูล ทุกอย่างพังทันที

**โจทย์ที่ 6** วัดด้วย `make eval` ซึ่งรันชุดคำถาม L3 ทั้งหมดและรายงานว่าข้อไหนผ่าน — ตรงกว่าการมีไฟล์เฉลย
