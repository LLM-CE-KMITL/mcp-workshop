#!/usr/bin/env python3
"""Workshop 3: MPLS NOC MCP Server - 6 tool จากวันที่ 2 ห่อด้วย FastMCP

    uv run python solutions/day3/workshop3_mcp_server.py

This is the reference solution for the final deliverable of the 3-day course.
It takes the 5 plain-function tools written by hand in
solutions/day2/workshop2_agent.py (lines 64-207), plus one semantic-search
tool written as Day 2's own exercise, and wraps each one with @mcp.tool so
any standard MCP client (Claude Desktop included) can call them - no bespoke
ReAct loop required any more. The logic inside every tool is copied
unchanged from Day 2; only the decorator, annotations and the model-facing
docstring are new (see Module 7 section 2.1 on writing tool descriptions for
a model rather than for a developer).

Deliberately NOT here: argparse, streamable-http transport, or anything from
apps/mcp-server/security/guardrails.py. Those are production concerns
covered in Module 8-10; this file is the minimum that runs over stdio for
one client (Claude Desktop) during the workshop.
"""

from __future__ import annotations

import csv
import io
import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase
from opensearchpy import OpenSearch

# Loaded before reading any env var below - running this script directly with
# `uv run` (not through docker compose --env-file) never sees .env otherwise.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

BANGKOK = timezone(timedelta(hours=7))

PG_DSN = os.getenv("PG_DSN",
                   "postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j_dev_password")
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
LOG_INDEX = os.getenv("OPENSEARCH_LOG_INDEX", "network-logs")
DOC_INDEX = os.getenv("OPENSEARCH_DOC_INDEX", "network-docs")

EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "baai/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed")

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
NOTIFY_TO = os.getenv("NOTIFY_TO", "noc@example.local")

OUTPUT_DIR = Path("data/reports")

mcp = FastMCP(name="mpls-noc-workshop3")


# ==========================================================================
# Tools (งานที่ 2) - logic เหมือนกับ solutions/day2/workshop2_agent.py ทุกประการ
# ==========================================================================

@mcp.tool(
    annotations={
        "title": "Search trouble tickets",
        "readOnlyHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
def search_tickets(status: str | None = None, days: int = 7,
                   limit: int = 20) -> dict:
    """ค้นหา ticket ที่ลูกค้าหรือวิศวกรแจ้งเข้ามา

    ใช้เมื่อต้องการรู้ว่ามีอะไรถูก "แจ้ง" เข้ามาบ้าง
    ห้ามใช้เพื่อดูพฤติกรรมของอุปกรณ์จริง - ให้ใช้ count_log_events แทน

    Args:
        status: open | in_progress | closed
        days: จำนวนวันย้อนหลัง
        limit: จำนวนผลลัพธ์สูงสุด

    Returns:
        dict ที่มี count (จำนวน ticket ที่พบ) และ tickets (รายการ ticket แต่ละใบ
        พร้อม ticket_id, severity, status, site_code, device_id, title, opened_at)
    """
    # โค้ดข้างในเหมือนฟังก์ชันเดิมจาก workshop2_agent.py:64-93 ทุกประการ
    since = datetime.now(BANGKOK) - timedelta(days=days)
    where = ["opened_at >= %s"]
    params: list = [since]
    if status:
        where.append("status = %s")
        params.append(status)

    with psycopg.connect(PG_DSN) as conn:
        cur = conn.cursor()
        cur.execute(
            f"""SELECT ticket_id, severity, status, site_code, device_id,
                       title, opened_at
                FROM tickets WHERE {' AND '.join(where)}
                ORDER BY opened_at DESC LIMIT %s""",
            tuple(params + [limit]),
        )
        rows = [
            {"ticket_id": r[0], "severity": r[1], "status": r[2],
             "site_code": r[3], "device_id": r[4], "title": r[5],
             "opened_at": r[6].isoformat()}
            for r in cur.fetchall()
        ]
    return {"count": len(rows), "tickets": rows}


@mcp.tool(
    annotations={
        "title": "Find shared upstream devices",
        "readOnlyHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
def get_upstream_devices(device_ids: list[str]) -> dict:
    """หาอุปกรณ์ upstream ที่อุปกรณ์หลายตัวใช้ร่วมกัน

    ใช้เมื่อลูกค้าหลายรายที่อยู่คนละอุปกรณ์แจ้งอาการเดียวกัน
    เพราะสาเหตุร่วมมักอยู่ที่อุปกรณ์ที่ทุกตัวพึ่งพา ซึ่ง ticket จะไม่เอ่ยถึง

    ห้ามใช้เมื่อรู้อยู่แล้วว่าอุปกรณ์ตัวไหนเป็นต้นเหตุ - เครื่องมือนี้มีไว้หา
    "จุดร่วม" ที่ยังไม่รู้เท่านั้น

    Args:
        device_ids: รายชื่อ device_id ที่จะหา upstream ร่วมกัน
            เช่น ["LPE-NBI-11", "LPE-NBI-12"]

    Returns:
        dict ที่มี upstream_devices (อุปกรณ์ upstream ทั้งหมดที่พบ เรียงจากจำนวน
        อุปกรณ์ที่พึ่งพามันมากไปน้อย) และ shared_by_all (เฉพาะอุปกรณ์ที่ทุกตัวใน
        device_ids พึ่งพาร่วมกัน - คือคำตอบของ "มีจุดร่วมกันหรือไม่")
    """
    # โค้ดข้างในเหมือนฟังก์ชันเดิมจาก workshop2_agent.py:96-125 ทุกประการ
    driver = GraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD),
    )
    with driver, driver.session() as session:
        records = session.run(
            """UNWIND $ids AS start
               MATCH (d:Device {device_id: start})-[:UPLINK_TO*1..4]->(up:Device)
               RETURN start, up.device_id AS upstream""",
            ids=device_ids,
        ).data()

    dependents: dict[str, set] = {}
    for record in records:
        dependents.setdefault(record["upstream"], set()).add(record["start"])

    shared = sorted(
        ({"device_id": k, "dependent_count": len(v), "depends_on_it": sorted(v)}
         for k, v in dependents.items()),
        key=lambda x: -x["dependent_count"],
    )
    common = [s for s in shared if s["dependent_count"] == len(set(device_ids))]
    return {"upstream_devices": shared, "shared_by_all": common}


@mcp.tool(
    annotations={
        "title": "Aggregate log events",
        "readOnlyHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
def count_log_events(days: int = 7, group_by: str = "device_id") -> dict:
    """นับ log events แยกตามอุปกรณ์หรือประเภทเหตุการณ์

    ใช้เมื่อถามว่า "กี่ครั้ง" หรือ "ตัวไหนเยอะที่สุด"
    ห้ามใช้เมื่อต้องการอ่านข้อความ log จริง - เครื่องมือนี้คืนแค่ตัวเลขสรุป
    ไม่คืนข้อความ log แต่ละบรรทัด

    Args:
        days: จำนวนวันย้อนหลังที่จะนับ
        group_by: ชื่อ field ที่จะใช้จัดกลุ่ม เช่น device_id, event_type, severity

    Returns:
        dict ที่มี total (จำนวน event ทั้งหมดที่ severity เป็น critical/error/
        warning ในช่วงเวลานั้น) และ results (รายการ {key, count} เรียงจากมากไปน้อย
        สูงสุด 15 กลุ่ม)
    """
    # โค้ดข้างในเหมือนฟังก์ชันเดิมจาก workshop2_agent.py:128-150 ทุกประการ
    client = OpenSearch(hosts=[OPENSEARCH_URL])
    response = client.search(
        index=f"{LOG_INDEX}-*",
        body={
            "size": 0,
            "query": {"bool": {"must": [
                {"range": {"@timestamp": {"gte": f"now-{days}d"}}},
                {"terms": {"severity": ["critical", "error", "warning"]}},
            ]}},
            "aggs": {"grouped": {"terms": {"field": group_by, "size": 15}}},
        },
    )
    return {
        "total": response["hits"]["total"]["value"],
        "results": [{"key": b["key"], "count": b["doc_count"]}
                    for b in response["aggregations"]["grouped"]["buckets"]],
    }


@mcp.tool(
    annotations={
        "title": "Generate a report file",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
def export_report(title: str, rows: list[dict], format: str = "markdown") -> dict:
    """แปลงข้อมูลเป็นไฟล์รายงาน (markdown หรือ csv) แล้วบันทึกลงดิสก์

    ใช้เมื่อต้องการไฟล์ที่ส่งต่อให้คนอื่นได้ (เช่นแนบไปกับ send_notification)
    ห้ามใช้เพื่อ "แสดงผล" ข้อมูลเฉยๆ - ถ้าผู้ใช้แค่อยากเห็นข้อมูล ให้ตอบใน
    ข้อความแทน ไม่ต้องสร้างไฟล์

    หมายเหตุ: tool นี้เขียนไฟล์ใหม่จริงในเครื่อง (data/reports/) จึงตั้ง
    readOnlyHint เป็น False - client ที่ดีควรถามผู้ใช้ก่อนอนุญาตให้เรียก

    Args:
        title: หัวข้อรายงาน
        rows: ข้อมูลที่จะใส่ในรายงาน แต่ละ dict คือหนึ่งแถว
        format: markdown (ค่าเริ่มต้น) หรือ csv

    Returns:
        dict ที่มี ok, path (ตำแหน่งไฟล์ที่สร้าง - ใช้ค่านี้เป็น attachment
        ให้ send_notification ได้ทันที), rows (จำนวนแถว), format
    """
    # โค้ดข้างในเหมือนฟังก์ชันเดิมจาก workshop2_agent.py:153-183 ทุกประการ
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(BANGKOK).strftime("%Y%m%d-%H%M%S")

    if format == "csv":
        buffer = io.StringIO()
        if rows:
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        path = OUTPUT_DIR / f"report-{stamp}.csv"
        # utf-8-sig so Excel on Windows renders Thai correctly. Without the
        # BOM every Thai character becomes mojibake, which is the single most
        # common complaint about exported reports.
        path.write_text(buffer.getvalue(), encoding="utf-8-sig")
    else:
        lines = [f"# {title}", "", f"สร้างเมื่อ {datetime.now(BANGKOK):%Y-%m-%d %H:%M}", ""]
        if rows:
            headers = list(rows[0].keys())
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "---|" * len(headers))
            for row in rows:
                lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
        path = OUTPUT_DIR / f"report-{stamp}.md"
        path.write_text("\n".join(lines), encoding="utf-8")

    return {"ok": True, "path": str(path), "rows": len(rows), "format": format}


@mcp.tool(
    annotations={
        "title": "Send a notification",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
def send_notification(subject: str, body: str, to: str | None = None,
                      attachment: str | None = None) -> dict:
    """ส่งอีเมลแจ้งเตือนไปที่ MailHog (ไม่ออกนอกเครื่อง ไม่ใช่กล่องจดหมายจริง)

    ใช้เป็นขั้นตอนสุดท้ายเมื่อผู้ใช้ขอให้ส่งผลให้ทีม NOC เท่านั้น
    ถ้าต้องแนบรายงาน ให้เรียก export_report ก่อนเสมอ แล้วใส่ path ที่ได้
    ลงใน attachment

    หมายเหตุ: tool นี้ส่งอีเมลจริง (แม้ปลายทางจะเป็น MailHog ในเครื่องก็ตาม)
    จึงตั้ง readOnlyHint เป็น False - client ที่ดีควรถามผู้ใช้ก่อนอนุญาตให้เรียก

    Args:
        subject: หัวเรื่องอีเมล
        body: เนื้อหาอีเมล
        to: ผู้รับ (ค่าเริ่มต้นคือ NOTIFY_TO ใน .env)
        attachment: path ของไฟล์ที่จะแนบ (เช่น path ที่ export_report คืนมา)

    Returns:
        dict ที่มี ok, to (ผู้รับจริง), inspect_at (URL ของ MailHog UI
        สำหรับตรวจว่าอีเมลส่งถึงจริง - http://localhost:8025)
    """
    # โค้ดข้างในเหมือนฟังก์ชันเดิมจาก workshop2_agent.py:186-207 ทุกประการ
    to = to or NOTIFY_TO
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = "agent@nt.local"
    message["To"] = to
    message.set_content(body)

    if attachment and Path(attachment).exists():
        data = Path(attachment).read_bytes()
        message.add_attachment(data, maintype="text", subtype="plain",
                               filename=Path(attachment).name)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.send_message(message)
    return {"ok": True, "to": to, "inspect_at": "http://localhost:8025"}


def _embed_query(text: str) -> list[float] | None:
    """Embed a search string using the same OpenAI-compatible /embeddings
    endpoint used throughout this project (EMBEDDING_BASE_URL / _MODEL /
    _DIM). Returns None if the endpoint is unavailable so the caller can
    degrade to keyword search instead of failing outright."""
    try:
        response = httpx.post(
            f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
            json={
                "model": EMBEDDING_MODEL,
                "input": [text],
                "dimensions": EMBEDDING_DIM,
            },
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]
    except Exception:  # noqa: BLE001
        return None


@mcp.tool(
    annotations={
        "title": "Search runbooks and configs by meaning",
        "readOnlyHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
def search_docs_semantic(query: str, limit: int = 5) -> dict:
    """ค้นหาเอกสารทางเทคนิค (runbook, config) ด้วยความหมาย ไม่ใช่คำที่ตรงตัว

    ใช้เมื่อถาม "ปกติแก้ปัญหานี้ยังไง" หรือ "มีเอกสารเรื่องนี้ไหม"
    เอกสารเขียนด้วยศัพท์ของวิศวกร ให้ถามด้วยศัพท์เชิงเทคนิคของอาการ ไม่ใช่
    คำพูดของลูกค้า

    ห้ามใช้เพื่อดูว่า "เกิดอะไรขึ้นจริง" - นั่นคือหน้าที่ของ count_log_events
    เครื่องมือนี้คืนความรู้/เอกสาร ไม่ใช่เหตุการณ์จริงที่เกิดขึ้น

    Args:
        query: คำอธิบายปัญหาหรือขั้นตอนที่ต้องการค้นหา เป็นภาษาธรรมชาติ
        limit: จำนวนผลลัพธ์สูงสุด

    Returns:
        dict ที่มี method (vector หรือ keyword_fallback ถ้า embedding endpoint
        ใช้งานไม่ได้) และ results (รายการเอกสารที่ใกล้เคียงที่สุด พร้อม title,
        content, score)
    """
    client = OpenSearch(hosts=[OPENSEARCH_URL])
    vector = _embed_query(query)

    if vector is None:
        # Degrade to keyword search rather than fail outright, matching the
        # pattern in apps/mcp-server/tools/logs.py:216-231.
        response = client.search(
            index=DOC_INDEX,
            body={"size": limit, "query": {"match": {"content": query}}},
        )
        return {
            "method": "keyword_fallback",
            "warning": "embedding endpoint unavailable, results are keyword based",
            "results": [
                {"title": h["_source"].get("title"),
                 "content": h["_source"].get("content"), "score": h["_score"]}
                for h in response["hits"]["hits"]
            ],
        }

    response = client.search(
        index=DOC_INDEX,
        body={"size": limit, "query": {"knn": {"embedding": {"vector": vector, "k": limit}}}},
    )
    hits = response["hits"]["hits"]
    if not hits:
        return {"method": "vector", "results": [],
                "note": "ยังไม่มี embedding ใน network-docs ให้รัน make reseed"}

    return {
        "method": "vector",
        "results": [
            {"title": h["_source"].get("title"),
             "source_type": h["_source"].get("source_type"),
             "device_id": h["_source"].get("device_id"),
             "content": h["_source"].get("content"),
             "score": h["_score"]}
            for h in hits
        ],
    }


# ==========================================================================
# Resource (งานที่ 3) - schema แบบ dict คงที่ ไม่ query โครงสร้างจริง
# ==========================================================================

@mcp.resource("schema://noc")
def noc_schema() -> str:
    """Which of the 6 tools in this server answers which kind of question.
    Read this first."""
    return json.dumps(
        {
            "system": "NT IP-MPLS network operations assistant (Workshop 3)",
            "routing_questions_to_stores": {
                "what was reported": "PostgreSQL via search_tickets",
                "what do these devices have in common": (
                    "Neo4j via get_upstream_devices"
                ),
                "how many / which is worst": "OpenSearch via count_log_events",
                "how do we normally fix this": "OpenSearch via search_docs_semantic",
                "make a file to hand off": "export_report (writes to data/reports/)",
                "tell the team": (
                    "send_notification (emails MailHog, inspect at "
                    "http://localhost:8025)"
                ),
            },
            "hard_rules": [
                "search_tickets tells you what was REPORTED, not what a device is "
                "actually doing - use count_log_events for that.",
                "get_upstream_devices only makes sense once you already have two "
                "or more device_id values in hand, usually from several tickets.",
                "export_report must run before send_notification whenever a "
                "report needs to be attached - pass its returned path as "
                "send_notification's attachment.",
                "export_report and send_notification have side effects "
                "(readOnlyHint: false) - every other tool here is read-only.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


# ==========================================================================
# Prompt (งานที่ 4) - บังคับลำดับการสืบสวน ไม่ใช่แค่พูดคำถามซ้ำ
# ==========================================================================

@mcp.prompt(title="ตรวจหาสาเหตุร่วมของ ticket")
def diagnose_shared_upstream(range: str = "last_14d") -> str:
    """หาสาเหตุร่วมของ ticket ที่มีอาการคล้ายกัน"""
    return f"""ช่วยหาสาเหตุร่วมของ ticket ที่แจ้งอาการคล้ายกันในช่วง {range}

ลำดับที่ต้องทำ:
1. เรียก search_tickets เพื่อดู ticket ในช่วงเวลานี้
2. รวบรวมอุปกรณ์ที่แต่ละ ticket เกี่ยวข้อง
3. เรียก get_upstream_devices กับอุปกรณ์เหล่านั้นทั้งหมดพร้อมกัน
4. สรุปว่ามีอุปกรณ์ต้นทางร่วมหรือไม่ พร้อมระบุว่าข้อสรุปมาจากขั้นตอนใด"""


if __name__ == "__main__":
    mcp.run(transport="stdio")
