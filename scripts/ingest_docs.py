from __future__ import annotations

import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import sys

import httpx
from dotenv import load_dotenv
from opensearchpy import OpenSearch

# Loaded before reading any env var below - running this script directly with
# `uv run` (not through docker compose --env-file) never sees .env otherwise,
# and LLM_API_KEY silently falls back to "not-needed", which OpenRouter rejects
# with 401.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# แก้ไขเป็น parents[1] เพื่อให้ชี้หา apps/agent-api ได้ถูกต้องเมื่อวางไว้ในโฟลเดอร์ scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "agent-api"))
from agent import tokenizer

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://admin:admin_dev_password@localhost:9200")
INDEX_NAME = "network-docs"
MAX_TOKENS_PER_CHUNK = 512

EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "baai/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Call the embedding endpoint. Without this, chunks land in OpenSearch

    with no `embedding` field, and search_docs_semantic's knn query can never
    match them even though the text is indexed and readable.
    """
    response = httpx.post(
        f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
        json={"model": EMBEDDING_MODEL, "input": texts},
        headers={"Authorization": f"Bearer {os.getenv('EMBEDDING_API_KEY') or os.getenv('LLM_API_KEY', 'not-needed')}"},
        timeout=90,
    )
    response.raise_for_status()
    ordered = sorted(response.json()["data"], key=lambda d: d["index"])
    vectors = [d["embedding"] for d in ordered]
    if vectors and len(vectors[0]) != EMBEDDING_DIM:
        raise SystemExit(
            f"Model returned {len(vectors[0])} dimensions but EMBEDDING_DIM is "
            f"{EMBEDDING_DIM}. Fix EMBEDDING_DIM in .env, and remember the "
            f"OpenSearch index template must match too."
        )
    return vectors


def _title_of(file_path: Path, content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return file_path.stem.replace("-", " ").replace("_", " ").title()

def _chunk_markdown_by_tokens(text: str, max_tokens: int = 400) -> list[str]:
    """
    แบ่ง chunk ตามหัวข้อ (##) ก่อน แล้วถ้าหัวข้อใดยาวเกิน max_tokens 
    ให้ซอยย่อยด้วยการนับ Token จริง เพื่อความสม่ำเสมอของขนาด Chunk
    """
    sections = text.split("\n## ")
    chunks = []
    
    for i, section in enumerate(sections):
        if i > 0:
            section = "## " + section
            
        if tokenizer.count(section) <= max_tokens:
            chunks.append(section.strip())
        else:
            lines = section.split("\n")
            current_chunk = []
            current_count = 0
            
            for line in lines:
                line_tokens = tokenizer.count(line + "\n")
                if current_count + line_tokens > max_tokens and current_chunk:
                    chunks.append("\n".join(current_chunk).strip())
                    current_chunk = [line]
                    current_count = line_tokens
                else:
                    current_chunk.append(line)
                    current_count += line_tokens
                    
            if current_chunk:
                chunks.append("\n".join(current_chunk).strip())
                
    return [c for c in chunks if c]

def main():
    print(f"\n=== เริ่มกระบวนการ Ingest เอกสารเข้า {INDEX_NAME} ===")
    
    client = OpenSearch(
        hosts=[OPENSEARCH_URL],
        http_auth=("admin", "admin_dev_password"),
        verify_certs=False,
        ssl_show_warn=False
    )
    
    docs_path = Path("data/mock_fs/runbooks")
    if not docs_path.exists():
        print(f"❌ ไม่พบโฟลเดอร์ {docs_path}")
        return

    warning_count = 0
    total_chunks = 0

    for file_path in docs_path.glob("*.md"):
        print(f"\n📄 กำลังประมวลผลไฟล์: {file_path.name}")
        content = file_path.read_text(encoding="utf-8")
        title = _title_of(file_path, content)
        doc_id = hashlib.sha256(file_path.name.encode("utf-8")).hexdigest()
        updated_at = datetime.now(timezone.utc).isoformat()

        chunks = _chunk_markdown_by_tokens(content, max_tokens=MAX_TOKENS_PER_CHUNK)
        vectors = embed_batch(chunks)

        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            total_chunks += 1

            n_tokens = tokenizer.count(chunk)

            if n_tokens > MAX_TOKENS_PER_CHUNK:
                print(f"  ⚠️ WARNING: Chunk #{idx} ยาว {n_tokens} tokens (เกินเกณฑ์ {MAX_TOKENS_PER_CHUNK})")
                warning_count += 1
            else:
                print(f"  ✅ Chunk #{idx}: {n_tokens} tokens")

            chunk_id = hashlib.sha256(f"{file_path.name}_{idx}_{chunk}".encode("utf-8")).hexdigest()

            doc_body = {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "chunk_index": idx,
                "title": title,
                "source_type": "runbook",
                "file_name": file_path.name,
                "content": chunk,
                "token_count": n_tokens,
                "updated_at": updated_at,
                "embedding": vector,
            }

            client.index(
                index=INDEX_NAME,
                id=chunk_id,
                body=doc_body,
                refresh=True
            )

    print(f"\n========================================")
    print(f"🎉 Ingest สำเร็จทั้งหมด {total_chunks} Chunks")
    print(f"⚠️ พบบันทึกเตือน Chunk ยาวเกินเกณฑ์: {warning_count} ชิ้น")
    print(f"========================================")

if __name__ == "__main__":
    main()