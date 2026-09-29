import os
import psycopg
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

EMB_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1")
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "baai/bge-m3")
PG = os.getenv("PG_ADMIN_DSN", "postgresql://mpls:mpls_dev_password@localhost:5432/mplsdb")

client = OpenAI(base_url=EMB_BASE_URL, api_key=os.getenv("LLM_API_KEY", ""))

def embed_batch(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=EMB_MODEL, input=texts)
    return [item.embedding for item in response.data]

# ดูค่าที่ดึงมาจาก .env จริง ๆ ก่อนรัน - ช่วยดีบั๊กเวลาผลลัพธ์ไม่ตรงที่คิดไว้
print(f"EMBEDDING_BASE_URL = {EMB_BASE_URL}")
print(f"EMBEDDING_MODEL    = {EMB_MODEL}")
print(f"PG_ADMIN_DSN       = {PG}")
print(f"LLM_API_KEY        = {'(ตั้งค่าแล้ว)' if os.getenv('LLM_API_KEY') else '(ว่างเปล่า! เช็ค .env)'}")

print("กำลังแปลงคำถามเป็น embedding...")
q = embed_batch(["ลูกค้าบ่นว่าอินเทอร์เน็ตหลุดบ่อย"])[0]
print("ความยาวมิติเวกเตอร์:", len(q))  # ควรจะได้ 1024

# `<=>` คือ cosine distance ใน pgvector - ยิ่งน้อยยิ่งใกล้
query_vec = "[" + ",".join(map(str, q)) + "]"
with psycopg.connect(PG) as conn:
    cur = conn.cursor()
    cur.execute(
        """SELECT ticket_id, title, embedding <=> %s::vector AS distance
           FROM tickets
           ORDER BY embedding <=> %s::vector
           LIMIT 5""",
        (query_vec, query_vec),
    )
    for ticket_id, title, distance in cur.fetchall():
        print(f"{distance:.4f}  {ticket_id}  {title}")
