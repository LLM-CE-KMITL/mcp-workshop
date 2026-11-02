# ADR-004: เข้าถึงข้อมูลผ่าน MCP server เดียว (in-process เป็นค่าเริ่มต้น)

- สถานะ: Accepted
- วันที่บันทึก: 2026-11-01 (บันทึกย้อนหลังจากโค้ดที่ใช้งานอยู่ ไม่ใช่เอกสารต้นฉบับของผู้ออกแบบ)

- **บริบท:** ต้องการให้ agent ของเรา, Claude Desktop, Cursor และ Claude Code ใช้ชุดเครื่องมือเดียวกันโดยไม่เขียนสองรอบ และ agent ไม่ควรคุยกับฐานข้อมูลโดยตรง
- **ตัดสินใจ:** รวม tool ทั้ง 3 ฐานข้อมูลไว้ใน server เดียว ([server.py](../../apps/mcp-server/server.py)) agent เรียกผ่าน [mcp_client.py](../../apps/agent-api/agent/mcp_client.py) โดยค่าเริ่มต้น import server มาเรียกใน process เดียวกัน (`in_process`) ผู้เรียนจึงไม่ต้องเปิดสอง terminal ส่วนโหมด `http` (Streamable HTTP) คือรูปแบบ production
- **ผลที่ตามมา:** (+) หนึ่ง tool list ให้โมเดลวางแผนข้ามระบบได้ดีขึ้น (−) โหมด in-process ใช้ค่าตั้งของ process เดียวกัน ถ้าแก้โค้ด server ต้อง restart agent
