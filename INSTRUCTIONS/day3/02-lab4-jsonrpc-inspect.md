# Lab 4 · ดู JSON-RPC ที่วิ่งจริง

**10:15 – 10:30** (15 นาที)

---

## เป้าหมาย

ทำให้ MCP ที่เคยเป็นแนวคิดเชิงนามธรรมกลายเป็นสิ่งที่จับต้องได้ ด้วยการพิจารณาข้อความจริงที่รับส่งระหว่าง client กับ server

---

## 1. ดูเวอร์ชันที่ใช้จริง

```bash
uv run python scripts/print_protocol_version.py
```

โปรดบันทึกเลข `protocolVersion` ที่ได้ไว้ เนื่องจากเอกสารทุกฉบับในคอร์สนี้อ้างอิงเลขเวอร์ชันจากคำสั่งนี้เสมอ มิได้กำหนดไว้ตายตัวในเอกสาร

---

## 2. ส่งคำขอ JSON-RPC ด้วยมือ

เริ่มต้นด้วยการรัน server แบบ HTTP ก่อน (คำสั่งนี้ใช้ได้เหมือนกันในทุกระบบปฏิบัติการ):

```bash
uv run python apps/mcp-server/server.py --transport streamable-http --port 9000
```

เปิด terminal ใหม่ แล้วดำเนินการ 3 ขั้นตอนต่อไปนี้ตามลำดับ — เลือกคำสั่งตามระบบปฏิบัติการที่ใช้งาน:

### 2.1 ส่งคำขอ `initialize`

#### macOS/Linux (curl)
```bash
curl -X POST http://localhost:9000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual","version":"1.0"}}}'
```

#### Windows (PowerShell)
```powershell
Invoke-RestMethod -Uri http://localhost:9000/mcp -Method Post -ContentType "application/json" -Headers @{"Accept"="application/json, text/event-stream"} -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual","version":"1.0"}}}'
```

### 2.2 ดูรายการ tool

#### macOS/Linux (curl)
```bash
curl -s http://localhost:8080/tools | python3 -m json.tool
```

#### Windows (PowerShell)
```powershell
Invoke-RestMethod -Uri http://localhost:8080/tools -Method Get | ConvertTo-Json -Depth 5
```

### 2.3 เรียก tool จริง (ผ่าน stdio transport โดยตรง ไม่ผ่าน HTTP)

#### macOS/Linux (bash)
```bash
payload='{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "workshop-client", "version": "1.0"}}}'

echo "$payload" | uv run python apps/mcp-server/server.py --transport stdio
```

#### Windows (PowerShell)
```powershell
$payload = '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "workshop-client", "version": "1.0"}}}'

Write-Output $payload | uv run python apps/mcp-server/server.py --transport stdio
```

---

## 3. ใช้ MCP Inspector

เครื่องมือที่เป็นทางการสำหรับตรวจสอบและทดสอบ MCP server โดยเปิดเป็น**หน้าเว็บ**ที่มีแท็บ Tools/Resources/Prompts ให้ทดสอบได้โดยตรง ไม่ใช่เพียงการส่งคำขอ JSON-RPC ทางเดียวตามข้อ 2 ด้านบน คำสั่งเดียวกันนี้ใช้ได้ทั้ง macOS/Linux/Windows เนื่องจากเป็นคำสั่ง `npx` (Node.js) ล้วน ไม่ใช่ syntax ที่ผูกกับ shell ใดชนิดหนึ่ง:

```bash
npx @modelcontextprotocol/inspector uv run python apps/mcp-server/server.py --transport stdio
```

โดยปกติทุกครั้งที่รัน Inspector จะสุ่ม token ใหม่และแสดง deep link ที่มี token แนบมาให้เปิดใช้งาน (เพื่อป้องกันไม่ให้ผู้อื่นในเครื่องเดียวกันเชื่อมต่อเข้ามาที่ backend ซึ่งสามารถ spawn process ได้) หากต้องเปิด/ปิดบ่อยครั้งระหว่างการทำแล็บและไม่ต้องการคัดลอก token ใหม่ทุกรอบ สามารถปิดการตรวจสอบนี้ได้ด้วย `DANGEROUSLY_OMIT_AUTH=true` — **ใช้เฉพาะเมื่อพัฒนาบนเครื่องของตนเองเท่านั้น ห้ามตั้งค่านี้ไว้ถาวรใน shell profile หรือใช้งานเมื่อแชร์เครื่องร่วมกับผู้อื่นหรือ deploy ใช้งานจริง** (ชื่อตัวแปร `DANGEROUSLY_...` ถูกตั้งใจให้ดูน่าเกรงขาม เพื่อเตือนถึงความเสี่ยงดังกล่าว)

#### macOS/Linux
```bash
DANGEROUSLY_OMIT_AUTH=true npx @modelcontextprotocol/inspector uv run python apps/mcp-server/server.py --transport stdio
```

#### Windows (PowerShell)
```powershell
$env:DANGEROUSLY_OMIT_AUTH="true"; npx @modelcontextprotocol/inspector uv run python apps/mcp-server/server.py --transport stdio
```

เปิดเบราว์เซอร์ตามที่ระบบแจ้งไว้ แล้วดำเนินการดังนี้:
- แท็บ **Tools** — เรียก `get_upstream_devices` ด้วย `["LPE-NBI-11","LPE-NBI-12","LPE-NBI-13"]`
- แท็บ **Resources** — อ่าน `clock://now` และ `schema://overview`
- แท็บ **Prompts** — ดูเทมเพลตที่มี
- ดู **raw JSON-RPC** ที่วิ่งจริงทุกครั้งที่กด

---

## 4. สิ่งที่ต้องสังเกต

- [ ] `initialize` ตอบกลับด้วย `protocolVersion` อะไร
- [ ] `tools/list` คืน `inputSchema` มาด้วย — **นี่คือสิ่งที่ทำให้โมเดลรู้ว่าต้องกรอกอะไร**
- [ ] `annotations` ของแต่ละ tool มี `readOnlyHint` ไหม
- [ ] `id` ในคำขอกับคำตอบตรงกัน
- [ ] `resources/read` คืนอะไรที่ต่างจาก `tools/call`

---

## 5. คำถามที่ต้องตอบได้

1. ถ้าส่ง request โดยไม่มี `id` จะเกิดอะไรขึ้น และเรียกว่าอะไร
2. `tools/list` กับ `resources/list` ต่างกันตรงไหนในเชิงการใช้งาน
3. ถ้า tool โยน exception client จะเห็นอะไร (ลองเรียก `get_device_config` ด้วยชื่อที่ไม่มีจริง)

---

## สิ่งที่ต้องส่ง

ผลลัพธ์ `initialize` + เลข `protocolVersion` + คำตอบ 3 ข้อข้างบน
