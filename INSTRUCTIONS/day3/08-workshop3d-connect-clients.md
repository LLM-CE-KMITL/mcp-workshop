# Workshop 3D · ต่อกับ Claude Desktop / Claude Code / Cursor

**14:45 – 15:00** (15 นาที)

---

## โจทย์

นำ MCP Server ที่สร้างขึ้นไปเชื่อมต่อกับ AI Client ระดับโลก จากนั้นสั่งงานด้วยภาษาธรรมชาติเพื่อให้ระบบดึงข้อมูลจริงจากฐานข้อมูลในเครื่อง

> **ช่วงนี้มักเป็นจุดที่ผู้เรียนรู้สึกว่าระบบใช้งานได้จริง** เนื่องจากเป็นครั้งแรกที่ได้เห็นเครื่องมือที่ใช้งานอยู่ทุกวันเรียกใช้โค้ดที่ตนเองเพิ่งเขียนขึ้น

---

## 1. Claude Desktop

แก้ไขไฟล์ config ดังนี้:

| ระบบ | ที่อยู่ |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "nt-network": {
      "command": "uv",
      "args": [
        "--directory", "/absolute/path/to/ai-mpls-workshop",
        "run", "python", "apps/mcp-server/server.py",
        "--transport", "stdio"
      ],
      "env": {
        "PG_DSN": "postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "neo4j_dev_password",
        "OPENSEARCH_URL": "http://localhost:9200"
      }
    }
  }
}
```
หากยังไม่มีไฟล์ ให้รันคำสั่ง `mkdir $env:APPDATA\Claude` ตามด้วย `notepad $env:APPDATA\Claude\claude_desktop_config.json` เพื่อสร้างไฟล์ดังกล่าว

**ต้อง restart Claude Desktop** ทุกครั้งหลังแก้ไข config

### ข้อควรระวัง

| ปัญหา | สาเหตุ |
|---|---|
| server ไม่ปรากฏในรายการ | ต้องใช้ **absolute path** เท่านั้น |
| server ปรากฏแต่เกิด error ทันที | มีการใช้ `print()` ไปยัง stdout ทั้งที่ stdout ถูกใช้งานโดยโปรโตคอล จึงควร log ไปยัง stderr แทน |
| เชื่อมต่อฐานข้อมูลไม่ได้ | Docker ยังไม่ได้เปิดใช้งาน หรือ env ใน config ไม่ครบถ้วน |

---

## 2. Claude Code 
```bash
irm https://claude.ai/install.ps1 | iex
```

```bash
claude mcp add nt-network -- uv --directory "$(pwd)" run python apps/mcp-server/server.py --transport stdio
```

```bash
claude mcp list
```

---

## 3. Cursor IDE

`.cursor/mcp.json` ในโปรเจกต์:

```json
{
  "mcpServers": {
    "nt-network": {
      "command": "C:/Users/ratta/mcp-workshop/.venv/Scripts/python.exe",
      "args": [
        "C:/Users/ratta/mcp-workshop/apps/mcp-server/server.py",
        "--transport",
        "stdio"
      ],
      "env": {
        "PG_DSN": "postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "neo4j_dev_password",
        "OPENSEARCH_URL": "http://localhost:9200"
      }
    }
  }
}
```
เข้าไปที่หน้าตั้งค่า แล้วค้นหาคำว่า `Model Context Protocol` ที่หัวข้อ Chat > Mcp > Discovery: Enabled จากนั้นคลิกเพื่อเปิดใช้งาน (Enable)

✅ Cursor workspace configuration ('.cursor/mcp.json') (cursor-workspace)
จากนั้นกด Ctrl + Shift + P ค้นหาคำว่า MCP แล้วเลือกเปิดใช้งาน nt-network

---

## 4. ทดสอบด้วยภาษาธรรมชาติ

ทดลองพิมพ์คำสั่งต่อไปนี้ใน client ที่เชื่อมต่อไว้แล้ว:

| ระดับ | คำสั่ง |
|---|---|
| ง่าย | *"ในระบบโครงข่ายมีอุปกรณ์อะไรบ้าง"* |
| กลาง | *"ticket ที่ยังไม่ปิดของนนทบุรีมีอะไรบ้าง"* |
| **ยาก** | *"ทำไมช่วงสองสัปดาห์นี้ถึงมีลูกค้าแจ้งเน็ตหลุดซ้ำๆ หลายราย"* |
| ทดสอบ Resource | *"ช่วยอ่าน schema ของฐานข้อมูลแล้วอธิบายว่าแต่ละตารางเก็บอะไร"* |
| ทดสอบ Prompt | เลือก prompt `diagnose_repeated_complaints` จากเมนู |
| ทดสอบ guardrail | *"ลบ ticket ที่ปิดแล้วทั้งหมด"* → ต้องถูกปฏิเสธ |

---

## 5. สิ่งที่ต้องสังเกต

```mermaid
flowchart LR
    A["คำถามเดียวกัน"] --> B["Chainlit ของเรา"]
    A --> C["Claude Desktop"]
    B --> D{"ผลต่างกันไหม"}
    C --> D
```

- Claude Desktop ใช้โมเดลที่แตกต่างจาก Qwen3.5 35B-A3B ดังนั้นลำดับเครื่องมือที่ถูกเลือกเรียกใช้อาจแตกต่างกัน
- Claude Desktop มี native tool calling ในตัว และเรียก tool แบบวนทีละขั้นในลักษณะเดียวกัน ความแตกต่างอยู่ที่ *กลไก* ที่ทำให้เกิด JSON สำหรับเรียก tool (native API เทียบกับ structured output ที่กำหนดขึ้นเอง) มิใช่ความแตกต่างที่สถาปัตยกรรมของการวนลูป
- `readOnlyHint` มีผลต่อการขออนุญาตก่อนเรียกใช้งาน ลองเรียก `generate_report` (ซึ่งมี `readOnlyHint: false`) แล้วสังเกตว่า client ถามยืนยันก่อนหรือไม่
- **Tool ชุดเดียวกันและโค้ดชุดเดียวกันสามารถทำงานได้กับ client ที่แตกต่างกันโดยสิ้นเชิง** — นี่คือคุณค่าสำคัญของ MCP

---

## เกณฑ์ผ่าน

- [ ] `nt-network` ปรากฏในรายการ MCP server ของ client อย่างน้อย 1 ตัว
- [ ] สั่งงานภาษาธรรมชาติแล้ว AI ไปดึงข้อมูลจริงจากฐานข้อมูลได้
- [ ] คำถามระดับยากได้คำตอบที่มี `APE-NBI-03`
- [ ] อ่าน Resource ได้
- [ ] เรียกใช้ Prompt template ได้
- [ ] คำสั่งลบข้อมูลถูกปฏิเสธ
- [ ] เทียบผลกับ Chainlit ของตัวเองแล้วอธิบายความต่างได้

---

## ต่อไป

→ [โจทย์ที่ 6: Cross-Service Diagnosis](12-challenge6-cross-service-diagnosis.md)
