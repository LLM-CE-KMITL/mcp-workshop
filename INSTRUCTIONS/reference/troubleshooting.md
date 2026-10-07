# การแก้ไขปัญหาที่พบบ่อย

---

## 1. ติดตั้งและเปิดระบบ

| อาการ | สาเหตุ | วิธีแก้ |
|---|---|---|
| OpenSearch restart วนไม่จบ | RAM ที่ให้ Docker น้อยเกินไป | Docker Desktop → Settings → Resources → Memory ≥ **8 GB** |
| `make up` ค้างที่ seeder | Neo4j ยังบูตไม่เสร็จ (ใช้เวลานานกว่าตัวอื่น) | รอ 60 วินาที ถ้ายังค้างให้ `make down && make up` |
| Port ชนกัน | มีบริการอื่นใช้ port อยู่ | `lsof -i :5432` แล้วปิด หรือแก้ port ใน `docker/docker-compose.yml` |
| `make verify` FAIL ทุกข้อ | seed ยังไม่ทำงาน | `make seed` แล้วดู log |
| pgAdmin ถามรหัสผ่านตอนเปิด server แล้วเข้าไม่ได้ | ใช้รหัสผ่านไม่ตรงกับบัญชีของ server นั้น หรือค่า `PG_PASSWORD` ใน `.env` ถูกเปลี่ยน | server `MPLS Workshop DB` ใช้บัญชี `mpls` / `mpls_dev_password` · server `... (read-only ...)` ใช้บัญชี `mcp_reader` / `mcp_reader_password` (ตรวจ `PG_PASSWORD` และ `PG_READONLY_PASSWORD` ใน `.env`) |
| `password authentication failed for user "mcp_reader"` พร้อมกับ Neo4j `0 node` และ OpenSearch `no such index [network-docs]` (พบบน Windows) | ไฟล์สคริปต์ถูกแปลงท้ายบรรทัดเป็น CRLF ทำให้ init ของ PostgreSQL ล้มเหลว จึงไม่มีตารางและไม่มีบัญชี `mcp_reader` แล้ว seeder ล้มตามไปด้วย | รัน `uv run python scripts/fix_line_endings.py --reset-db` (รายละเอียดในหัวข้อ "Windows: ฐานข้อมูลว่างและไม่มีบัญชี mcp_reader" ด้านล่าง) |

### Windows: ฐานข้อมูลว่างและไม่มีบัญชี `mcp_reader`

**อาการ** (มักพบพร้อมกัน): ตารางสถานะในหน้าแชตแสดง PostgreSQL เป็น 🔴 `password authentication failed for user "mcp_reader"`, Neo4j แสดง `0 node · 0 relationship`, OpenSearch แสดง `no such index [network-docs]` และเมื่อตรวจด้วย `docker exec mpls-postgres psql -U mpls -d mplsdb -c "\du"` จะไม่พบบัญชี `mcp_reader`

**สาเหตุ:** Git บน Windows มักแปลงท้ายบรรทัดของไฟล์เป็น CRLF ตอน clone สคริปต์ `docker/postgres/init/02_schema.sh` ซึ่งรันใน container Linux จึงล้มเหลว การ init ของ PostgreSQL (ซึ่งรันเพียงครั้งเดียวตอนสร้าง volume) หยุดก่อนสร้างตาราง ข้อมูลอ้างอิง และบัญชี `mcp_reader` จากนั้น container สตาร์ตใหม่โดยข้าม init เพราะมีข้อมูลอยู่แล้ว ฐานข้อมูลจึงว่างทั้งที่สถานะเป็น healthy และ seeder ล้มที่คำสั่ง INSERT แรก

**ตรวจยืนยัน:** หากผลลัพธ์มี `w/crlf` แสดงว่าไฟล์ถูกแปลงเป็น CRLF (ปกติต้องเป็น `w/lf`)

```powershell
git ls-files --eol docker/postgres/init/02_schema.sh docker/demo/entrypoint.sh
```

**วิธีแก้:** รันสคริปต์จากโฟลเดอร์โปรเจกต์ สคริปต์จะแปลงไฟล์เป็น LF แล้วล้างฐานข้อมูลเพื่อให้ init ทำงานใหม่ โดยจะถามให้พิมพ์ `yes` ก่อนลบข้อมูล

```bash
uv run python scripts/fix_line_endings.py --reset-db
```

เมื่อเสร็จ ให้ทำ [หัวข้อ 1 ของ 05-setup.md](../day0/05-setup.md) ใหม่ตั้งแต่ต้น (เปิดฐานข้อมูล, `up seeder` ให้จบ) แล้วตรวจด้วย `verify.py`

- **ดูก่อนโดยไม่แก้ไฟล์:** `uv run python scripts/fix_line_endings.py --check`
- **คำเตือน:** `--reset-db` ลบข้อมูลทั้งหมดใน volume ของ workshop (PostgreSQL, Neo4j, OpenSearch, pgAdmin) ซึ่ง seed ใหม่ได้ ต้องล้างด้วย เพราะสคริปต์ init รันเฉพาะตอน volume ว่าง แก้ไฟล์อย่างเดียวไม่มีผล
- **ป้องกันการเกิดซ้ำ:** ก่อน clone ครั้งถัดไป ให้ตั้งค่า `git config --global core.autocrlf input` เพื่อไม่ให้ Git แปลงเป็น CRLF
- **หากยังไม่ใช่สาเหตุนี้:** ตรวจว่ามี PostgreSQL ที่ติดตั้งเป็น Windows service ครองพอร์ต 5432 อยู่หรือไม่ ด้วย `netstat -ano | findstr :5432` (ควรเป็นโปรเซสของ Docker เท่านั้น)

---

## 2. LLM และ Embedding

| อาการ | สาเหตุ | วิธีแก้ |
|---|---|---|
| `Connection refused` ไปที่ LLM | ยังไม่ได้ต่อ VPN หรือ URL ผิด | `curl $LLM_BASE_URL/models` ทดสอบก่อน · URL **ต้องลงท้ายด้วย `/v1`** |
| ตอบช้ามาก | หลายคนใช้ GPU ตัวเดียวกัน | ระหว่าง lab ใช้ `LLM_MODEL=$LLM_MODEL_FAST` |
| `[WARN] ticket embeddings empty` | embedding endpoint ต่อไม่ได้ตอน seed | `make embed-tickets && make embed-devices` |
| JSON ที่ได้ไม่ผ่าน schema บ่อย (เช่น `Field required` หรือ `Invalid JSON` จนเกิด `Could not obtain valid ... after 3 attempts`) | gateway รับ `response_format` โดยไม่แสดง error แต่ไม่ได้บังคับจริง โมเดลจึงตอบเป็นข้อความธรรมดาหรือขาดฟิลด์ (พบกับ `qwen3-30b-a3b` ผ่าน OpenRouter) หรือ container ยังใช้ image ที่มีโค้ดเก่า | ตรวจว่า `complete_structured()` ใน `agent/llm.py` ฝัง schema ลงใน prompt **ทุกครั้ง** (ไม่ใช่เฉพาะตอนที่การเรียก API ล้มเหลว) · การตั้ง `LLM_GUIDED_DECODING=false` เพียงอย่างเดียว**ไม่ช่วย** · หากรันผ่าน container ให้ build ใหม่ด้วย `docker compose -f docker/docker-compose.yml --env-file .env --profile demo up -d --build mcp-demo` · อาการอาจเกิดเป็นครั้งคราวได้เพราะโมเดลมีการสุ่ม กลไก retry อัตโนมัติจะช่วยแก้ได้ในกรณีส่วนใหญ่ |
| `usage` ไม่มีใน stream | gateway ไม่รองรับ `stream_options` | นับเองด้วย `agent/tokenizer.py` |
| มิติ embedding ไม่ตรง | โมเดลคนละตัวกับที่ตั้งไว้ | ตรวจ `EMBEDDING_DIM` ให้ตรงกับ column และ mapping ทั้งสามที่ |

---

## 3. MCP Server

| อาการ | สาเหตุ | วิธีแก้ |
|---|---|---|
| **Claude Desktop ไม่เห็น server** | ใช้ relative path ใน config | ต้องเป็น **absolute path** เท่านั้น |
| **server ขึ้นแล้ว error ทันที** | มี `print()` ลง stdout | stdout เป็นของโปรโตคอล ให้ log ลง **stderr** |
| tool ทำงานแต่ข้อมูลว่าง | container ยังไม่ได้เปิด | `docker ps` ตรวจว่าครบ |
| `ModuleNotFoundError` เมื่อรันผ่าน client | ไม่ได้อยู่ใน environment เดียวกัน | ใช้ `uv --directory <abs> run python ...` |
| tool ถูกปฏิเสธทั้งที่ไม่ควร | keyword filter จับคำในข้อมูล | ตรวจ `_WRITE_KEYWORDS` — ต้อง match เป็นคำเต็ม |

---

## 4. Agent

| อาการ | สาเหตุ | วิธีแก้ |
|---|---|---|
| โมเดลเลือก tool ที่ไม่มีจริง | ไม่มี validate ล่วงหน้าเหมือน plan-then-execute อีกต่อไป | เพิ่มการตรวจสอบใน `react.py` ก่อนเรียก - ถ้า `tool` ไม่อยู่ใน `list_tools()` ให้ป้อน error กลับเป็น observation แทนที่จะเรียกจริง |
| Agent วนไม่จบ | Loop Guard ไม่ทำงาน | ตรวจว่าเรียก `guard.check()` **ก่อน**ทุกครั้งที่เรียก tool - ใน ReAct นี่คือแนวป้องกันด่านเดียวที่เหลืออยู่ |
| ตอบว่าไม่ทราบทั้งที่มีข้อมูลอยู่จริง | ผลลัพธ์ถูกตัดจนหมด | เพิ่ม `MCP_MAX_ROWS` หรือใช้ `count_log_events` แทน |
| context ขยายขนาดไม่หยุด | ไม่ตรวจการเปลี่ยนเรื่อง | ดู [day2/lab3](../day2/06-lab3-context-memory.md) |
| **คำถามนอกขอบเขตล้าง context** | ตรวจ topic shift ก่อน intent | สลับลำดับ — **intent ต้องมาก่อนเสมอ** |
| อ้างวันที่ผิด | โมเดลเดาวันที่เอง | ให้อ่าน `clock://now` ก่อนตัดสินใจก้าวแรก · รับเฉพาะช่วงเวลาสัมพัทธ์ |

---

## 5. UI

| อาการ | สาเหตุ | วิธีแก้ |
|---|---|---|
| **stream ค้าง ไม่มีข้อมูลปรากฏ** | ลืมบรรทัดว่างท้าย SSE | ต้องลงท้ายด้วย `\n\n` |
| event หายบางส่วน | parse ทีละ chunk | ต้อง buffer แล้วแยกที่ `\n\n` เอง |
| Step ไม่ปิด | ไม่ได้เรียก `__aexit__` | ต้องเรียกทุกครั้ง แม้ตอน error |
| ภาษาไทยแสดงผลผิดเพี้ยนใน CSV | Excel ไม่อ่าน UTF-8 | เขียนด้วย `utf-8-sig` |

---

## 6. ข้อมูล

| อาการ | สาเหตุ | วิธีแก้ |
|---|---|---|
| **ถาม "24 ชั่วโมงที่ผ่านมา" แล้วไม่พบข้อมูล** | seed ไว้นานแล้ว | `make reseed` — ทำทุกเช้าวันเดโม |
| ข้อมูลไม่ตรงกับ scenario | แก้ scenario แต่ไม่ได้ seed ใหม่ | `make reseed && make verify` |
| ผลลัพธ์ต่างกันทุกครั้งที่รัน test | ไม่ได้ตรึงเวลา | ตั้ง `DEMO_NOW` และ `SEED_RANDOM_SEED=42` |

---

## 7. คำสั่งช่วยวินิจฉัย

```bash
docker compose -f docker/docker-compose.yml ps
```

```bash
docker compose -f docker/docker-compose.yml logs --tail 50 opensearch
```

```bash
curl -s localhost:9200/_cluster/health | python3 -m json.tool
```

```bash
make verify
```

---

## 8. การเริ่มต้นใหม่ทั้งหมด

```bash
make reset && make up && make verify
```
