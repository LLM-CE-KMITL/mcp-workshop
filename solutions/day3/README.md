# เฉลยวันที่ 3

> ⚠️ อ่านก่อนลอง = เสียโอกาสเรียนรู้ · ดูวิธีใช้ที่ [../README.md](../README.md)

**ไม่มีไฟล์เฉลยแยกในโฟลเดอร์นี้โดยตั้งใจ** — เพราะเฉลยของวันที่ 3 คือระบบที่ทำงานอยู่จริง

| โจทย์ | เฉลยอยู่ที่ |
|---|---|
| [Workshop 3A: MCP Server](../../INSTRUCTIONS/day3/05-workshop3a-mcp-server.md) | `apps/mcp-server/` |
| [Workshop 3B: Agent API](../../INSTRUCTIONS/day3/06-workshop3b-agent-api.md) | `apps/agent-api/main.py` |
| [Workshop 3C: Chainlit](../../INSTRUCTIONS/day3/07-workshop3c-chainlit.md) | `apps/chainlit-ui/` |
| [โจทย์ที่ 5: Guardrail Red-team](../../INSTRUCTIONS/day3/04-challenge5-guardrail-redteam.md) | `tests/test_guardrails.py` |
| [โจทย์ที่ 6: Cross-Service](../../INSTRUCTIONS/day3/12-challenge6-cross-service-diagnosis.md) | `uv run python eval/run_eval.py` |

---

## วิธีทำ Workshop 3 ให้ได้ประโยชน์เต็มที่

โค้ดใน `apps/` ทำงานได้อยู่แล้วและเป็นตัวเดียวกับที่ container เดโมใช้
หากเปิดอ่านก่อนเริ่ม จะเหลือเพียงการคัดลอกโค้ด

**แนวทางที่ควรทำแทน**

```bash
cp -r apps/mcp-server /tmp/mcp-server-reference
```

แล้วเขียนโค้ดของตนเองใน `apps/mcp-server/` โดยเริ่มจาก:

1. `server.py` + `config.py` + `db.py` — โครงพื้นฐาน
2. `tools/tickets.py` เพียง **1 tool** ให้ทำงานได้ก่อน
3. ทดสอบด้วย MCP Inspector ให้ผ่าน
4. แล้วค่อยเติมที่เหลือตาม pattern เดิม

เมื่อเสร็จสิ้นให้เทียบกับ `/tmp/mcp-server-reference`

---

## 5 จุดที่ควรอ่านเมื่อเทียบผลงาน

### 1. `security/guardrails.py` — ชั้นป้องกันที่ prompt injection ไม่สามารถเอาชนะได้

```python
def assert_read_only(query: str, tool: str) -> None:
```

ฟังก์ชันนี้รันแม้ในกรณีที่บัญชีฐานข้อมูลเป็น read-only อยู่แล้ว — ถือเป็น defence in depth
บัญชีปกป้องข้อมูล ส่วนฟังก์ชันนี้ปกป้องกรณีที่มีการตั้งค่าผิดพลาดในอนาคต และสร้าง audit log ที่อ่านแล้วเข้าใจได้ง่าย

**บั๊กจริงที่พบตอนเขียน test**: `\bpassword\b` ไม่ match `PG_PASSWORD` เพราะขีดล่างเป็น word character — ทำให้รหัสผ่านอาจรั่วไหลไปกับผลลัพธ์ของ tool ได้ ดูวิธีแก้ที่ `_SECRET_NAME`

### 2. `clock.py` — "ตอนนี้" มาจากข้อมูล ไม่ใช่นาฬิกา

```python
def data_now(refresh: bool = False) -> datetime:
```

และ tool รับเฉพาะช่วงเวลาสัมพัทธ์ (`last_7d`) ไม่รับวันที่ absolute
เพราะ **วันที่ใดก็ตามที่โมเดลคำนวณขึ้นเอง คือวันที่ที่มีโอกาสผิดพลาดได้เสมอ**

### 3. `tools/network.py` → `get_upstream_devices` — คำนวณให้ ไม่ใช่ให้โมเดลคิด

Tool นี้ไม่ได้คืนแค่ path แต่หา intersection ให้โดยตรง พร้อมฟิลด์ `interpretation` ในรูปแบบภาษาที่มนุษย์เข้าใจได้ง่าย

> **หลักการทั่วไป**: งานที่สามารถเขียนเป็นโค้ดได้อย่างแน่นอน ไม่ควรปล่อยให้โมเดลเป็นผู้ดำเนินการ

### 4. `tools/reports.py` — allowlist ไม่ใช่ deny-list

```python
ALLOWED_SCRIPTS: dict[str, dict] = {...}
subprocess.run(argv, shell=False, timeout=30)
```

"ชื่อสคริปต์" ต้องเป็นชุดปิดที่นักพัฒนากำหนด ไม่ใช่ string ที่โมเดลส่งมา
และ `shell=False` เสมอ — `shell=True` คือการเปิดช่องให้ประกอบคำสั่งใหม่

### 5. `resources/schemas.py` — ทำไม schema เป็น Resource ไม่ใช่ Tool

โมเดลควร**อ่านก่อนเริ่มคิด** ไม่ใช่ต้องตัดสินใจว่าจะเรียกหรือไม่

ผลที่วัดได้: โมเดลที่อ่าน schema แล้วจะไม่เดาชื่อ column และไม่สร้างตารางที่ไม่มีอยู่จริงขึ้นมาเอง

---

## ตรวจงานตัวเอง

```bash
make test -- tests/test_mcp_tools.py
```

```bash
make eval
```
