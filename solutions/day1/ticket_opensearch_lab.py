#!/usr/bin/env python3
"""Module 2 reference solution: index tickets into OpenSearch and search with kNN.

    uv run python solutions/day1/ticket_opensearch_lab.py

This is the exact script from INSTRUCTIONS/day1/02-module2-embeddings-opensearch.md
("### ขั้นตอน"), saved here as the reference solution for the lab. It:
    1. creates the `tickets-lab` knn_vector index in OpenSearch (if missing)
    2. embeds every row of the `tickets` table (title + description) via the
       project's OpenAI-compatible embedding endpoint
    3. bulk-indexes the vectors into OpenSearch
    4. runs a natural-language kNN query against the index and prints the
       top matches with their similarity scores
"""
from __future__ import annotations

import os

import httpx
import psycopg
from dotenv import load_dotenv
from opensearchpy import OpenSearch, helpers

load_dotenv()

PG_DSN = os.getenv(
    "PG_DSN", "postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb"
)
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "baai/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed")

# ชื่อ index ของ lab นี้โดยเฉพาะ แยกจาก network-docs / network-logs ที่มีอยู่แล้ว
TICKET_INDEX = "tickets-lab"


def embed_many(texts: list[str]) -> list[list[float]]:
    """เรียก embedding endpoint แบบเดียวกับที่ docker/seeder/embed.py ใช้จริง"""
    response = httpx.post(
        f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
        json={"model": EMBEDDING_MODEL, "input": texts},
        headers={"Authorization": f"Bearer {LLM_API_KEY}"},
        timeout=60,
    )
    response.raise_for_status()
    # ต้องเรียงตาม index เอง - API ไม่รับประกันลำดับ (บทเรียนจาก embed.py)
    ordered = sorted(response.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in ordered]


def ensure_index(client: OpenSearch) -> None:
    if client.indices.exists(index=TICKET_INDEX):
        return
    client.indices.create(
        index=TICKET_INDEX,
        body={
            "settings": {"index.knn": True},
            "mappings": {
                "properties": {
                    "ticket_id": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "severity": {"type": "keyword"},
                    "site_code": {"type": "keyword"},
                    "device_id": {"type": "keyword"},
                    "title": {"type": "text"},
                    "description": {"type": "text"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": EMBEDDING_DIM,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "lucene",
                            "parameters": {"ef_construction": 128, "m": 16},
                        },
                    },
                }
            },
        },
    )


def main() -> None:
    client = OpenSearch(hosts=[OPENSEARCH_URL], http_compress=True, timeout=60)
    ensure_index(client)

    with psycopg.connect(PG_DSN) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT ticket_id, category, severity, site_code, device_id, title, description
               FROM tickets ORDER BY ticket_id"""
        )
        rows = cur.fetchall()

    print(f"Embedding {len(rows)} tickets...")
    batch = 32
    actions = []
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        vectors = embed_many([f"{title}\n\n{desc}" for *_, title, desc in chunk])
        for (ticket_id, category, severity, site_code, device_id, title, desc), vec in zip(
            chunk, vectors
        ):
            actions.append(
                {
                    "_index": TICKET_INDEX,
                    "_id": ticket_id,
                    "_source": {
                        "ticket_id": ticket_id,
                        "category": category,
                        "severity": severity,
                        "site_code": site_code,
                        "device_id": device_id,
                        "title": title,
                        "description": desc,
                        "embedding": vec,
                    },
                }
            )

    helpers.bulk(client, actions)
    client.indices.refresh(index=TICKET_INDEX)
    print(f"Indexed {len(actions)} tickets into '{TICKET_INDEX}'")

    # ---------- ค้นหาด้วย kNN ----------
    query_text = "ลูกค้าแจ้งเน็ตหลุดเป็นช่วง ๆ ที่ไซต์ NBI"
    query_vector = embed_many([query_text])[0]

    result = client.search(
        index=TICKET_INDEX,
        body={
            "size": 5,
            "query": {"knn": {"embedding": {"vector": query_vector, "k": 5}}},
        },
    )
    print(f"\nคำค้น: {query_text}\n")
    for hit in result["hits"]["hits"]:
        src = hit["_source"]
        print(f"  {hit['_score']:.3f}  {src['ticket_id']}  [{src['category']}]  {src['title']}")


if __name__ == "__main__":
    main()
