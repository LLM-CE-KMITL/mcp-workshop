import asyncio
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
import psycopg
from dotenv import load_dotenv

# ต้องโหลด .env ก่อน import agent.llm เสมอ เพราะ agent/llm.py อ่าน
# LLM_BASE_URL/LLM_API_KEY เป็นค่าคงที่ระดับโมดูลตอน import - ถ้าโหลดทีหลัง
# มันจะได้ default "not-needed" ไปแล้ว แล้วยิง request ไปเจอ 401 Missing
# Authentication header ที่ OpenRouter (เจอบ่อยที่สุดตอนรันสคริปต์นี้ตรงๆ)
load_dotenv(Path(__file__).resolve().parent / ".env")

# เพิ่ม Path ไปยังโฟลเดอร์ agent-api
sys.path.insert(0, str(Path(__file__).resolve().parent / "apps" / "agent-api"))
from agent import llm

PG_DSN = os.getenv("PG_ADMIN_DSN", "postgresql://mpls:mpls_dev_password@localhost:5432/mplsdb")

# ==========================================
# 1. Schema กำหนดโครงสร้างข้อมูล
# ==========================================
class Category(str, Enum):
    LINK_DOWN = "link_down"
    INTERMITTENT = "intermittent"
    SLOW = "slow"
    CONFIG = "config"
    MAINTENANCE = "maintenance"
    INQUIRY = "inquiry"

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class TicketExtraction(BaseModel):
    category: Category
    severity: Severity
    affected_device: str | None = Field(None, description="รหัสอุปกรณ์ เช่น LPE-NBI-11 ถ้าไม่มีให้เป็น null")
    affected_site: str | None = Field(None, description="BKK หรือ NBI เท่านั้น")
    summary_th: str = Field(description="สรุปภาษาไทยไม่เกิน 2 ประโยค")
    customer_impact: str = Field(description="ผลกระทบต่อการใช้งานของลูกค้า")
    confidence: float = Field(ge=0.0, le=1.0)

# โครงสร้างผลลัพธ์ตามโจทย์เป๊ะ
class ExtractionResult(BaseModel):
    ok: bool
    data: TicketExtraction | None = None
    attempts: int
    errors: list[str]
    total_tokens: int
    latency_ms: int
    fallback_used: bool = False


# ==========================================
# 2. คลาส StructuredExtractor 
# ==========================================
class StructuredExtractor:
    def __init__(self, schema, model=None, max_retries=3, temperature=0.0):
        self.schema = schema
        self.model = model
        self.max_retries = max_retries
        self.temperature = temperature

    async def extract(self, text: str) -> ExtractionResult:
        stats = llm.LLMStats()
        json_schema = self.schema.model_json_schema()
        
        messages = [
            {
                "role": "system",
                "content": (
                    "คุณคือ AI สกัดข้อมูล Ticket เน็ตเวิร์ก จงแปลงบทสนทนานี้เป็น JSON ตาม Schema เท่านั้น "
                    "ห้ามใส่ข้อความอื่นนอกเหนือจาก JSON\n"
                    f"Schema: {json_schema}"
                )
            },
            {"role": "user", "content": text}
        ]

        errors_log = []
        fallback_used = False

        for attempt in range(1, self.max_retries + 1):
            print(f"\n  🔄 รอบที่ {attempt}")
            try:
                # เรียกใช้ LLM ผ่านโมดูลกลางพร้อมเก็บ Stats (Token & Latency)
                raw_response = await llm.complete(
                    messages=messages,
                    stats=stats,
                    model=self.model,
                    temperature=self.temperature
                )
                print(f"     raw response: {raw_response.strip()[:300]}")

                # ทำความสะอาด Markdown Fence ถ้ามี
                clean_raw = raw_response.strip()
                if clean_raw.startswith("```"):
                    clean_raw = clean_raw.split("```")[1]
                    if clean_raw.startswith("json"):
                        clean_raw = clean_raw[4:]
                clean_raw = clean_raw.strip()

                # ตรวจสอบความถูกต้องด้วย Pydantic Schema
                parsed_data = self.schema.model_validate_json(clean_raw)
                print(f"     ✅ parse ผ่าน: {parsed_data.model_dump()}")

                stats_dict = stats.as_dict()
                return ExtractionResult(
                    ok=True,
                    data=parsed_data,
                    attempts=attempt,
                    errors=errors_log,
                    total_tokens=stats_dict["total_tokens"],
                    latency_ms=stats_dict["latency_ms"],
                    fallback_used=fallback_used
                )

            except Exception as exc:
                error_msg = str(exc)
                errors_log.append(error_msg)
                print(f"     ❌ parse ไม่ผ่าน: {error_msg[:300]}")

                # ส่งประวัติที่ผิดพลาดกลับไปให้ LLM แก้ตัวเองในรอบถัดไป
                messages.append({"role": "assistant", "content": raw_response[:1000] if 'raw_response' in locals() else ""})
                messages.append({
                    "role": "user",
                    "content": f"JSON ไม่ผ่านการตรวจสอบ Validation Error: {error_msg}\nกรุณาแก้ไขและส่งเฉพาะ JSON ที่ถูกต้องเท่านั้น"
                })

        # ถ้ายอมแพ้หลังจากลองจนครบจำนวนครั้ง
        stats_dict = stats.as_dict()
        return ExtractionResult(
            ok=False,
            data=None,
            attempts=self.max_retries,
            errors=errors_log,
            total_tokens=stats_dict["total_tokens"],
            latency_ms=stats_dict["latency_ms"],
            fallback_used=fallback_used
        )


# ==========================================
# 3. ทดสอบดึงข้อมูลจริงจาก PostgreSQL ตาม SQL ในโจทย์
# ==========================================
async def main():
    print("กำลังเชื่อมต่อฐานข้อมูลเพื่อดึง Ticket จริง...")
    
    with psycopg.connect(PG_DSN) as conn:
        cur = conn.cursor()
        # ใช้ SQL Query ตามโจทย์เป๊ะเพื่อดึงบทสนทนาของแต่ละ Ticket
        rows = cur.execute("""
            SELECT t.ticket_id, 
                   string_agg(m.author_role || ': ' || m.message, E'\n' ORDER BY m.created_at) AS conversation
            FROM tickets t JOIN ticket_messages m ON m.ticket_id = t.ticket_id
            GROUP BY t.ticket_id LIMIT 3;
        """).fetchall()

    extractor = StructuredExtractor(schema=TicketExtraction)

    for ticket_id, conversation in rows:
        print(f"\n----------------------------------------")
        print(f"📌 กำลังประมวลผล Ticket ID: {ticket_id}")
        print(f"📥 บทสนทนาดิบ (raw_text):\n{conversation}")

        result = await extractor.extract(conversation)
        
        print(f"สถานะ (OK): {result.ok}")
        print(f"จำนวนรอบที่ใช้ (Attempts): {result.attempts}")
        print(f"เวลาที่ใช้ (Latency): {result.latency_ms} ms | Tokens: {result.total_tokens}")
        if result.errors:
            print(f"ข้อผิดพลาดที่พบ: {result.errors}")
        
        if result.ok and result.data:
            print("ผลลัพธ์ที่สกัดได้:")
            print(result.data.model_dump_json(indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())