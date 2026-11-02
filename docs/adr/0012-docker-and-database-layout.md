# ADR-012: โครงสร้าง Docker และฐานข้อมูล

- สถานะ: Accepted
- วันที่บันทึก: 2026-11-01 (บันทึกย้อนหลังจากโค้ดที่ใช้งานอยู่ ไม่ใช่เอกสารต้นฉบับของผู้ออกแบบ)
- ADR ที่เกี่ยวข้อง: [ADR-006](0006-swappable-openai-compatible-gateway.md)

- **บริบท:** ผู้เรียนต้องเปิดระบบทั้งชุดได้ด้วยคำสั่งไม่กี่บรรทัดบนเครื่องที่ต่างกัน (macOS/Windows)
- **ตัดสินใจ:** ใช้ compose ไฟล์เดียวที่มี profile (`demo`, `llm`) แยก `seeder` เป็นงานครั้งเดียว (PostgreSQL → Neo4j → OpenSearch) ใช้ init script ของ Postgres (`01`, `02_schema.sh`, `03`, `99_readonly_role.sql`) สร้างโครงสร้างและ role `mcp_reader` ด้วยรหัสผ่านค่าเริ่มต้นคงที่ (สคริปต์อ่านจาก GUC ไม่ใช่ env) image เดโมฝัง `apps/` ตอน build
- **ผลที่ตามมา:** (+) เริ่มได้เร็วและทำซ้ำได้ (−) init script รันครั้งเดียวต่อ volume ถ้าล้มครึ่งทางต้อง `make reset` ไฟล์ที่เป็น CRLF บน Windows ทำให้ `02_schema.sh` ล้ม (จึงมี `fix_line_endings.py`) ควรพิจารณาเพิ่ม `.gitattributes` บังคับ LF ต้องรัน seeder ก่อนจึงจะมี Neo4j node และ index `network-docs`
