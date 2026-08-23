#!/usr/bin/env python3
"""Backfill device profile embeddings in Neo4j.

    make embed-devices

Neo4j 5 has native vector indexes. The reason this project embeds devices at
all - rather than relying only on pgvector and OpenSearch - is that Neo4j is
the only store where a semantic hit can be followed by a graph traversal in
the same query.
"""

from __future__ import annotations

import os
import sys

import httpx
from neo4j import GraphDatabase

EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "http://localhost:11434/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embeddinggemma:300m")


def embed_batch(texts: list[str]) -> list[list[float]]:
    response = httpx.post(
        f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
        json={"model": EMBEDDING_MODEL, "input": texts},
        timeout=90,
    )
    response.raise_for_status()
    ordered = sorted(response.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in ordered]


def main() -> int:
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"),
              os.getenv("NEO4J_PASSWORD", "neo4j_dev_password")),
    )
    with driver, driver.session() as session:
        for label, key in (("Device", "device_id"), ("Circuit", "circuit_id")):
            records = session.run(
                f"MATCH (n:{label}) WHERE n.profile_text IS NOT NULL "
                f"RETURN n.{key} AS id, n.profile_text AS text"
            ).data()
            if not records:
                print(f"  no {label} nodes with profile_text - run `make seed` first")
                continue

            vectors = embed_batch([r["text"] for r in records])
            for record, vector in zip(records, vectors):
                session.run(
                    f"MATCH (n:{label} {{{key}: $id}}) SET n.embedding = $vec",
                    id=record["id"], vec=vector,
                )
            print(f"  embedded {len(records)} {label} nodes")

        count = session.run(
            "MATCH (n) WHERE n.embedding IS NOT NULL RETURN count(n) AS n"
        ).single()["n"]
        print(f"\n  {count} nodes now carry embeddings\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
