# รัน LLM ในองค์กร — Ollama vs vLLM

---

## 1. แนวทางการเลือกใช้งาน

```mermaid
flowchart TD
    Q{"จำนวนผู้ใช้งานพร้อมกัน"} -->|1-2 คน| O["Ollama<br/>ติดตั้งง่าย เริ่มเร็ว"]
    Q -->|"หลายคนพร้อมกัน"| V["vLLM<br/>continuous batching"]
    V --> P["Production"]
    O --> D["Dev / ทดลอง"]
```

| | Ollama | vLLM |
|---|---|---|
| ติดตั้ง | ง่ายมาก | ต้องตั้งค่ามากกว่า |
| หลายคนพร้อมกัน | จำกัด | **ดีกว่ามาก (continuous batching)** |
| Throughput | ปานกลาง | **สูง** |
| Quantization | GGUF ในตัว | AWQ / GPTQ / FP8 |
| Guided decoding | `format` รับ JSON Schema | `guided_json` / `response_format` |
| OpenAI-compatible | ✅ | ✅ |
| เหมาะกับ | dev, ทดลอง, เดโมคนเดียว | **production, ห้องอบรม 20 คน** |

> **สำหรับ workshop 20 คน แนะนำ vLLM** — Ollama จัดคิวได้จำกัด ทำให้ผู้ใช้คนที่ 15 ต้องรอเป็นเวลานาน

---

## 2. Ollama

```bash
docker compose -f docker/docker-compose.yml --profile llm up -d ollama
```

```bash
docker exec mpls-ollama ollama pull qwen/qwen3-30b-a3b
docker exec mpls-ollama ollama pull qwen/qwen3-30b-a3b
docker exec mpls-ollama ollama pull baai/bge-m3
```

```
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=not-needed
```

| ตัวแปรที่ควรตั้ง | หน้าที่ |
|---|---|
| `OLLAMA_KEEP_ALIVE=24h` | ไม่ให้ unload โมเดล — คำถามแรกจะไม่ช้า |
| `OLLAMA_NUM_PARALLEL=4` | จำนวนคำขอที่ทำพร้อมกัน |

---

## 3. vLLM

```bash
docker run --gpus all -p 8000:8000 \
  vllm/vllm-openai:latest \
  --model qwen/qwen3-30b-a3b \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90
```

```
LLM_BASE_URL=http://localhost:8000/v1
```

| ตัวเลือกสำคัญ | ผล |
|---|---|
| `--max-model-len` | ยิ่งยาว KV cache ยิ่งกิน VRAM → รองรับคนพร้อมกันได้น้อยลง |
| `--gpu-memory-utilization` | สัดส่วน VRAM ที่ยอมให้ใช้ |
| `--tensor-parallel-size` | กระจายข้าม GPU หลายใบ |
| `--quantization awq` | ลด VRAM แลกกับคุณภาพเล็กน้อย |

---

## 4. VRAM ที่ต้องการโดยประมาณ

| โมเดล | FP16 | 8-bit | 4-bit |
|---|---|---|---|
| Qwen3.5 35B-A3B | ~9 GB | ~5 GB | ~3 GB |
| Qwen3.5 35B-A3B | ~25 GB | ~13 GB | ~7 GB |
| **Qwen3.5 35B-A3B** | **~55 GB** | **~28 GB** | **~16 GB** |

**บวก KV cache** ซึ่งเพิ่มขึ้นตามความยาว context และจำนวนคำขอที่ทำพร้อมกัน

> โน้ตบุ๊กทั่วไปไม่สามารถรันโมเดลขนาด 27B ได้ จำเป็นต้องใช้เซิร์ฟเวอร์กลางที่ทุกคนเรียกใช้งานร่วมกัน

---

## 5. การตรวจสอบความพร้อมใช้งาน — 3 ข้อที่ต้องผ่านก่อนวันอบรม

### 5.1 ตรวจสอบการเชื่อมต่อ

```bash
curl -s $LLM_BASE_URL/models -H "Authorization: Bearer $LLM_API_KEY"
```

### 5.2 ตรวจสอบการรองรับ guided decoding ← **สำคัญที่สุด**

```bash
curl -s $LLM_BASE_URL/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen/qwen3-30b-a3b",
       "messages":[{"role":"user","content":"severity ของเหตุการณ์ link down"}],
       "response_format":{"type":"json_schema","json_schema":{"name":"r","schema":
         {"type":"object","properties":{"severity":{"type":"string",
          "enum":["low","medium","high","critical"]}},"required":["severity"]}}}}'
```

หากไม่รองรับ ให้ตั้งค่า `LLM_GUIDED_DECODING=false` และใช้ auto-retry แทน (ซึ่งจะทำให้ระบบช้าลงและใช้ token มากขึ้น)

### 5.3 ตรวจสอบว่าคืนค่า usage ระหว่าง stream หรือไม่

```bash
curl -s $LLM_BASE_URL/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen/qwen3-30b-a3b","messages":[{"role":"user","content":"hi"}],
       "stream":true,"stream_options":{"include_usage":true}}' | tail -3
```

หากไม่มี `usage` อยู่ในก้อนข้อมูลสุดท้าย ระบบมาตรวัดจะคำนวณเองด้วย `agent/tokenizer.py`

---

## 6. การปรับแต่งให้รองรับผู้ใช้งานหลายคนพร้อมกัน

| ปัญหา | วิธีแก้ |
|---|---|
| คำถามแรกช้ามาก | อุ่นเครื่องด้วยคำขอเปล่าตอนเริ่มระบบ |
| คนที่ 10 ขึ้นไปรอนาน | ใช้ vLLM · เพิ่ม instance · ลด `--max-model-len` |
| VRAM เต็ม | ลด context length · quantize · ใช้โมเดลเล็กสำหรับงานง่าย |
| ระหว่าง lab ช้าเกินไป | ให้ทุกคนใช้ `LLM_MODEL_FAST` แล้วสลับเป็น 27B ตอนส่งงาน |

---

## 7. LiteLLM Proxy — เมื่อมีหลาย backend

```mermaid
flowchart LR
    A["แอปทั้งหมด"] --> LP["LiteLLM Proxy"]
    LP --> O["Ollama (dev)"]
    LP --> V["vLLM (prod)"]
    LP --> M["Metric + rate limit ต่อผู้ใช้"]
```

ข้อดี: จำกัดโควตาต่อผู้เรียนได้ · เก็บสถิติการใช้รวมศูนย์ · สลับ backend โดยไม่แก้โค้ดแอป
