# ภาพรวมสถาปัตยกรรม

หน้านี้คือจุดเริ่มต้นของเอกสารชุดนี้ ควรอ่านทำความเข้าใจภาพรวมของสิ่งที่จะสร้างขึ้นตลอด 3 วัน ก่อนไปพิจารณาตัวอย่างข้อมูลจริงและเตรียมเครื่องในลำดับถัดไป
หน้านี้ยังไม่ต้องรันคำสั่งใด ๆ เพียงพิจารณาภาพรวมให้เข้าใจ

---

## 1. สิ่งที่จะสร้างตลอด 3 วัน

```mermaid
flowchart TB
    subgraph D1["วันที่ 1 — ควบคุม LLM"]
        A1["นับ token ให้ถูกตัว"]
        A2["สร้าง embedding<br/>+ vector index เอง"]
        A3["บังคับ JSON schema<br/>+ auto-retry"]
    end
    subgraph D2["วันที่ 2 — Agent"]
        B1["Intent Gate"]
        B2["ReAct Loop<br/>+ Loop Guard"]
        B3["Memory<br/>+ topic shift"]
    end
    subgraph D3["วันที่ 3 — MCP"]
        C1["MCP Server<br/>Tools/Resources/Prompts"]
        C2["Guardrails"]
        C3["ต่อ Claude Desktop<br/>/ Cursor"]
    end
    A2 --> B3
    A3 --> B2
    B2 --> C1
    D1 --> D2 --> D3
```

**องค์ประกอบของแต่ละวันถูกนำไปใช้ต่อในวันถัดไปทั้งหมด** ไม่มีส่วนใดที่จัดทำแล้วไม่ได้ใช้งานต่อ — ตารางเวลาเต็มทั้ง 3 วันสามารถดูได้ที่ [README.md](../../README.md)

---

## 2. สถาปัตยกรรมปลายทาง

นี่คือสถาปัตยกรรมที่ทุกโมดูลข้างต้นประกอบรวมกันเป็น เมื่อสิ้นสุดวันที่ 3:

```mermaid
flowchart TB
    U([ผู้ใช้]) --> UI["Chainlit UI :8000"]
    UI -->|HTTP + SSE| API["Agent API :8080"]

    subgraph CORE["Agent Core"]
        direction LR
        I["Intent Gate"] --> M["Memory"]
        M --> R["ReAct Loop<br/>(Thought → Action → Observation)<br/>+ Loop Guard"]
        R --> S["Synthesizer"]
        S --> G["Grounding"]
    end

    API --> CORE
    CORE -->|OpenAI protocol| LLM[["Qwen3-30B-A3B<br/>(ผ่าน OpenRouter)"]]
    CORE -->|MCP JSON-RPC 2.0| MCP["MCP Server<br/>nt-network"]

    MCP --> PG[("PostgreSQL<br/>+ pgvector")]
    MCP --> NEO[("Neo4j<br/>+ vector index")]
    MCP --> OS[("OpenSearch<br/>+ knn_vector")]

    CD["Claude Desktop /<br/>Claude Code / Cursor"] -->|MCP stdio| MCP
```

### จุดที่ควรสังเกต

- **Agent ไม่เคยคุยกับฐานข้อมูลโดยตรง** ทุกอย่างผ่าน MCP → server ตัวเดียวใช้ได้ทั้งกับ Agent API และกับ Claude Desktop
- **มี vector search ทั้ง 3 ฐาน** ซึ่งเป็นบทเรียนเปรียบเทียบของวันที่ 3
- **Grounding อยู่หลัง Synthesizer** ตรวจคำตอบก่อนถือว่าจบ

---

## 3. การไหลของหนึ่งคำถาม

ตัวอย่างแสดงให้เห็นว่าคำถามหนึ่งข้อเดินทางผ่านทุกองค์ประกอบในแผนภาพข้างต้นอย่างไร:

```mermaid
sequenceDiagram
    autonumber
    participant U as ผู้ใช้
    participant API as Agent API
    participant L as LLM
    participant M as MCP Server
    participant DB as ฐานข้อมูล 3 ตัว

    U->>API: คำถาม
    API->>L: จำแนก intent
    L-->>API: in_scope
    Note over API: ถ้า out_of_scope จบตรงนี้<br/>ไม่แตะฐานข้อมูลเลย
    API->>API: ตรวจว่าเปลี่ยนเรื่องไหม
    API->>M: อ่าน clock://now + schema://overview
    loop ReAct: ทีละขั้น จนกว่าจะพอตอบ
        API->>L: คิดขั้นต่อไป (บังคับ JSON schema)
        L-->>API: Thought + เครื่องมือที่จะเรียก (หรือ null ถ้าพอแล้ว)
        API->>M: เรียก tool
        M->>DB: query แบบ read-only
        DB-->>M: ผลลัพธ์
        M-->>API: ผลลัพธ์ (ตัดจำนวน + กรองความลับแล้ว)
        Note over API: ผลลัพธ์กลายเป็น observation<br/>ของรอบคิดถัดไปทันที
    end
    API->>L: สังเคราะห์คำตอบจากหลักฐาน
    L-->>U: คำตอบ stream ทีละ token
    API->>L: ตรวจว่าคำตอบมีหลักฐานรองรับไหม
```

---

## 4. Model Stack

โมเดลทั้งหมดที่ปรากฏในแผนภาพข้างต้น (`LLM`) มาจากชุดนี้ ซึ่งกำหนดไว้ล่วงหน้าแล้วใน `.env.example` ผู้เรียนไม่จำเป็นต้องเลือกเอง:

| บทบาท | โมเดล | เมื่อไหร่ใช้ |
|---|---|---|
| Main brain | `qwen/qwen3-30b-a3b` | ตอนส่งงานและเดโม |
| Iteration | `qwen/qwen3-30b-a3b` | ระหว่างวนแก้โค้ดใน lab (เร็วกว่ามาก) |
| Embedding | `baai/bge-m3` (1024 มิติ) | Lab 1 และ RAG |
| Rerank | `mxbai-rerank` | Lab วันที่ 3 |

การสลับไปใช้โมเดลที่เร็วขึ้นระหว่างทำ lab: ตั้งค่า `LLM_MODEL=$LLM_MODEL_FAST` ใน `.env` แล้วรีสตาร์ต `make api`

---

## 5. ข้อมูลที่ใช้ตลอด 3 วัน

ฐานข้อมูลทั้ง 3 ตัวในแผนภาพข้างต้นถูก seed ด้วยข้อมูลจำลองในขนาดนี้ (ตัวอย่างข้อมูลจริงดูเพิ่มเติมได้ที่ [02-initial-data.md](02-initial-data.md)):

| | จำนวน | Production จริง |
|---|---|---|
| อุปกรณ์ | 10 | 2,600+ |
| พื้นที่ | 2 (BKK, NBI) | ทั่วประเทศ |
| Log | 2,000 บรรทัด / 30 วัน | 29 GB/วัน |
| Ticket | 120 ใบ / 90 วัน | ประวัติจริง |

ความแตกต่างเมื่อขยายขนาดสู่ระบบจริงอยู่ใน [day3/13-scale-notes.md](../day3/13-scale-notes.md)
และการเปรียบเทียบกับระบบ production อยู่ใน [reference/production-mapping.md](../reference/production-mapping.md)

---

## ถัดไป

พิจารณาตัวอย่างข้อมูลจริงในฐานข้อมูลทั้ง 3 ที่ [02-initial-data.md](02-initial-data.md)
