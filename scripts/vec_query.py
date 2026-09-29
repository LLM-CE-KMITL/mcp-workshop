#!/usr/bin/env python3
"""CLI demo: แปลงคำค้นภาษาธรรมชาติเป็น embedding แล้วพิมพ์ query statement
ที่พร้อมก็อปไปรันเองใน pgAdmin / Neo4j Browser / OpenSearch Dev Tools -
สคริปต์นี้ไม่เชื่อมต่อฐานข้อมูลใดๆ เอง แค่สร้าง query ให้

ตัวอย่างคำค้นที่สมจริงกับแต่ละระบบ (แต่ละฝั่งมี dataset คนละแบบ):

    # pg / opensearch ค้นใน "tickets" - คำค้นควรเป็นอาการที่ลูกค้าแจ้ง
    uv run python scripts/vec_query.py pg "ลูกค้าแจ้งเน็ตหลุดเป็นช่วงๆ ที่ไซต์ NBI"
    uv run python scripts/vec_query.py opensearch "ลูกค้าแจ้งเน็ตหลุดเป็นช่วงๆ ที่ไซต์ NBI"

    # neo4j --label device ค้นใน "profile_text" ของอุปกรณ์ - คำค้นควรเป็นบทบาท/ตำแหน่งอุปกรณ์
    uv run python scripts/vec_query.py neo4j "อุปกรณ์ core router ที่เชื่อมต่อ backbone ระหว่างไซต์"

    # neo4j --label circuit ค้นใน "profile_text" ของวงจร - คำค้นควรเป็นสเปควงจร
    uv run python scripts/vec_query.py neo4j "วงจร MPLS-VPN ความเร็ว 50 Mbps" --label circuit

pg คือ query สำหรับตาราง tickets (Lab: Vector ใน PostgreSQL), neo4j คือ query
สำหรับ device_embedding (Lab: Vector ใน Neo4j - ใช้ --label circuit สำหรับ
circuit_embedding), opensearch คือ query สำหรับ index tickets-lab (Module 2)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ต้อง load ก่อนอ่าน env var ใดๆ ด้านล่าง - รันตรงด้วย `uv run` (ไม่ผ่าน
# docker compose --env-file) จะไม่เห็น .env โดยอัตโนมัติ
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "baai/bge-m3")


def embed(text: str) -> list[float]:
    response = httpx.post(
        f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
        json={"model": EMBEDDING_MODEL, "input": [text]},
        headers={"Authorization": f"Bearer {os.getenv('LLM_API_KEY', 'not-needed')}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


def round4(vector: list[float]) -> list[float]:
    """ปัดเศษ 4 ตำแหน่งเพื่อให้ query อ่านง่ายพอวางแล้วดูได้ - ผลต่างจากค่าเต็ม
    มีผลต่อ similarity เล็กน้อยมาก ไม่กระทบอันดับผลลัพธ์ในทางปฏิบัติ"""
    return [round(v, 4) for v in vector]


PER_LINE = 20  # จำนวนตัวเลขต่อบรรทัดตอนพิมพ์ vector


def wrap_vector(vector: list[float], indent: str = "") -> str:
    """คืน '[v1,v2,...,\\n  v21,...]' แบ่งบรรทัดทุก PER_LINE ตัว - vector 1024
    มิติถ้าอยู่บรรทัดเดียวยาวเกิน 8000 ตัวอักษร ซึ่ง editor บางตัว (พบแล้วกับ
    OpenSearch Dev Tools) วางแล้ว copy/paste ตัดข้อความขาดกลางบรรทัด ทำให้
    query ไม่ครบ - แบ่งเป็นหลายบรรทัดสั้นๆ ป้องกันปัญหานี้ โดยไม่ถึงกับพิมพ์
    ทีละตัวต่อบรรทัดจนยาวเป็นพันบรรทัดเหมือน json.dumps(indent=2)"""
    rows = [
        ",".join(str(v) for v in vector[i:i + PER_LINE])
        for i in range(0, len(vector), PER_LINE)
    ]
    return "[" + (",\n" + indent).join(rows) + "]"


def build_pg_query(vector: list[float], top_k: int) -> str:
    literal = wrap_vector(round4(vector))
    return (
        f"SELECT ticket_id, title, embedding <=> '{literal}'::vector AS distance\n"
        f"FROM tickets\n"
        f"WHERE embedding IS NOT NULL\n"
        f"ORDER BY distance\n"
        f"LIMIT {top_k};"
    )


def build_neo4j_query(vector: list[float], top_k: int, label: str) -> str:
    index_name = f"{label}_embedding"
    id_field = "device_id" if label == "device" else "circuit_id"
    literal = wrap_vector(round4(vector))
    return (
        f"CALL db.index.vector.queryNodes('{index_name}', {top_k}, {literal})\n"
        f"YIELD node, score\n"
        f"RETURN node.{id_field} AS id, score;"
    )


def build_opensearch_query(vector: list[float], top_k: int, index_name: str) -> str:
    # vector เป็น array 1024 ตัวเลข - json.dumps(indent=2) ปกติจะขึ้นบรรทัดใหม่
    # ทุกตัว ทำให้ query ยาวเป็นพันบรรทัด ส่วนอยู่บรรทัดเดียวก็ยาวเกิน 8000
    # ตัวอักษรจนบาง editor (เช่น OpenSearch Dev Tools) วางแล้วตัดข้อความขาด
    # จึงแบ่งเป็นหลายบรรทัดสั้นๆ ด้วย wrap_vector() แทน
    vector_literal = wrap_vector(round4(vector), indent="          ")
    body = (
        "{\n"
        f'  "size": {top_k},\n'
        '  "query": {\n'
        '    "knn": {\n'
        '      "embedding": {\n'
        f'        "vector": {vector_literal},\n'
        f'        "k": {top_k}\n'
        "      }\n"
        "    }\n"
        "  }\n"
        "}"
    )
    return f"GET {index_name}/_search\n" + body


def main() -> int:
    parser = argparse.ArgumentParser(
        description="แปลงคำค้นเป็น embedding แล้วพิมพ์ query statement "
                    "พร้อมก็อปไปรันเองใน pgAdmin / Neo4j Browser / OpenSearch Dev Tools"
    )
    parser.add_argument("backend", choices=["pg", "neo4j", "opensearch"])
    parser.add_argument("query", help='คำค้นภาษาธรรมชาติ เช่น "ระบบล่มบ่อย"')
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--label", choices=["device", "circuit"], default="device",
        help="เฉพาะ backend=neo4j: device_embedding (ค่าเริ่มต้น) หรือ circuit_embedding",
    )
    parser.add_argument(
        "--index", default="tickets-lab",
        help="เฉพาะ backend=opensearch: ชื่อ index (ค่าเริ่มต้น tickets-lab จาก Module 2)",
    )
    args = parser.parse_args()

    vector = embed(args.query)

    if args.backend == "pg":
        statement = build_pg_query(vector, args.top_k)
    elif args.backend == "neo4j":
        statement = build_neo4j_query(vector, args.top_k, args.label)
    else:
        statement = build_opensearch_query(vector, args.top_k, args.index)

    print("\n" * 4 + statement + "\n" * 4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
