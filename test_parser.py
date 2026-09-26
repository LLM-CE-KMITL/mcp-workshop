import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# ต้องโหลด .env ก่อน import agent.llm เสมอ เพราะ agent/llm.py อ่าน
# LLM_BASE_URL/LLM_API_KEY เป็นค่าคงที่ระดับโมดูลตอน import - ถ้าโหลดทีหลัง
# มันจะได้ default "not-needed" ไปแล้ว แล้วยิง request ไปเจอ 401 Missing
# Authentication header ที่ OpenRouter (เจอบ่อยที่สุดตอนรันสคริปต์นี้ตรงๆ)
load_dotenv(Path(__file__).resolve().parent / ".env")

sys.path.insert(0, 'apps/agent-api')

from pydantic import BaseModel, Field
from agent import llm

# 1. สร้าง Schema กำหนดโครงสร้าง Output ด้วย Pydantic
class TicketSummary(BaseModel):
    category: str = Field(description="ประเภทของปัญหา เช่น intermittent, offline, latency")
    severity: str = Field(description="ระดับความรุนแรง เช่น high, medium, low")
    affected_device: str = Field(description="ชื่ออุปกรณ์ที่ได้รับผลกระทบ (ถ้ามี)")
    affected_site: str = Field(description="ชื่อสาขาหรือไซต์ที่ได้รับผลกระทบ")
    summary_th: str = Field(description="สรุปปัญหาที่เกิดขึ้นเป็นภาษาไทยสั้นๆ")
    customer_impact: str = Field(description="ผลกระทบต่อการใช้งานของลูกค้า")
    confidence: float = Field(description="ความมั่นใจในการสรุปข้อมูล (0.0 ถึง 1.0)")

# 2. สร้าง Class สำหรับนำ Input ไปประมวลผล
class TicketParser:
    async def parse(self, text: str) -> TicketSummary:
        messages = [
            {
                "role": "system",
                "content": (
                    "คุณคือผู้เชี่ยวชาญด้าน IT Support จงสกัดข้อมูลจากข้อความแจ้งปัญหาของลูกค้า "
                    "และสรุปออกมาเป็นโครงสร้าง JSON ตามที่กำหนด"
                )
            },
            {
                "role": "user",
                "content": text
            }
        ]
        
        # ใช้ complete_structured เพื่อบังคับ Output และทำ Auto-correction
        result = await llm.complete_structured(messages, TicketSummary)
        return result

# 3. ฟังก์ชันทดสอบรันการทำงาน
async def main():
    parser = TicketParser()
    
    # จำลองข้อความดิบที่ลูกค้ารายงานมา (ไทยปนอังกฤษ ไม่มีโครงสร้าง)
    raw_text = "ลูกค้าสาขา NBI โทรมาโวยวายว่าเน็ตหลุดเป็นช่วงๆ ตั้งแต่เช้า ใช้งาน video conference ไม่ต่อเนื่องเลย แจ้งให้เช็คเร้าเตอร์ LPE-NBI-11 ด่วนๆ"

    print("📥 ข้อความดิบ (raw_text):")
    print(raw_text)

    print("\nกำลังประมวลผล...")
    structured_data = await parser.parse(raw_text)
    
    # พิมพ์ผลลัพธ์ออกมาดูในรูปแบบ JSON
    print("\n✅ ผลลัพธ์ที่ได้:")
    print(structured_data.model_dump_json(indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())