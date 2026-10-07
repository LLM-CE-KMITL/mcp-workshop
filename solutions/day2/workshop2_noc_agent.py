#!/usr/bin/env python3
"""Workshop 2 reference solution: the full NOC ReAct agent.

    python workshop2_noc_agent.py
    python workshop2_noc_agent.py "ลูกค้าหลายรายในโซน NBI แจ้งว่าอินเทอร์เน็ตหลุดเป็นช่วงๆ..."

This file starts from `solutions/day2/workshop2_agent.py` (its five tools and
its ~200-line ReAct loop are copied here verbatim, per the workshop
instructions - that base file is never edited) and adds exactly what
Workshop 2 asks for:

  1. A sixth tool, `search_docs_semantic`, doing a real kNN search over the
     `network-docs*` OpenSearch index (Module 6).
  2. An Intent Gate in front of the loop: `intent.classify()` rejects
     out-of-scope / ambiguous questions before any tool is ever called
     (Module 7).
  3. Session memory across turns: `run_turn(session_id, goal)` carries
     conversation context through `agent.memory`, detects topic shifts, and
     lets a short follow-up ("แล้วอุปกรณ์ที่เจอมีกี่ตัว") be answered from
     context instead of starting the investigation over (Module 8).
  4. A full Thought/Action/Observation trace written to
     data/reports/trace-<goal-slug>-<timestamp>.json on every run.

Capabilities required by the curriculum: search, convert a file, send email,
plus semantic search, intent screening and cross-turn memory.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv
from neo4j import GraphDatabase
from opensearchpy import OpenSearch
from pydantic import BaseModel, Field

def _find_repo_root(start: Path) -> Path:
    """Walk up from this file until the project root is found.

    This file is meant to live at the project root per the workshop
    instructions, but the reference copy under solutions/day2/ sits two
    levels deeper - a fixed parents[N] would only be correct for one of the
    two locations. Anchoring on pyproject.toml instead makes it work from
    either place.
    """
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return start.parent


# Loaded before reading any env var below, and before importing agent.* -
# agent.llm builds its OpenAI client from LLM_API_KEY at import time, so this
# must run first or that client is permanently built with "not-needed".
REPO_ROOT = _find_repo_root(Path(__file__).resolve())
load_dotenv(REPO_ROOT / ".env")

# apps/agent-api holds the real Module 7 / Module 8 code (intent.py,
# memory.py) plus the top-level schemas.py they both import from. Adding it
# to sys.path lets us reuse that code directly instead of re-implementing it.
sys.path.insert(0, str(REPO_ROOT / "apps" / "agent-api"))
from agent import intent  # noqa: E402
from agent import memory as agent_memory  # noqa: E402

BANGKOK = timezone(timedelta(hours=7))
PG_DSN = os.getenv("PG_DSN",
                   "postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3-30b-a3b")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "baai/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
OPENSEARCH_DOC_INDEX = os.getenv("OPENSEARCH_DOC_INDEX", "network-docs")
OUTPUT_DIR = REPO_ROOT / "data" / "reports"

MAX_STEPS = 8
MAX_SAME_TOOL = 3


# ==========================================================================
# 1. Tools - first five copied verbatim from workshop2_agent.py
# ==========================================================================

def search_tickets(status: str | None = None, days: int = 7,
                   limit: int = 20) -> dict:
    """ค้นหา ticket ที่ถูกแจ้งเข้ามา

    ใช้เมื่อต้องการรู้ว่ามีอะไรถูก "แจ้ง" เข้ามาบ้าง
    อย่าใช้เพื่อดูพฤติกรรมของอุปกรณ์ - ให้ใช้ count_log_events แทน
    """
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


def get_upstream_devices(device_ids: list[str]) -> dict:
    """หาอุปกรณ์ upstream ที่อุปกรณ์หลายตัวใช้ร่วมกัน

    ใช้เมื่อลูกค้าหลายรายที่อยู่คนละอุปกรณ์แจ้งอาการเดียวกัน
    เพราะสาเหตุร่วมมักอยู่ที่อุปกรณ์ที่ทุกตัวพึ่งพา ซึ่ง ticket จะไม่เอ่ยถึง
    """
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"),
              os.getenv("NEO4J_PASSWORD", "neo4j_dev_password")),
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


def count_log_events(days: int = 7, group_by: str = "device_id") -> dict:
    """นับ log events แยกตามอุปกรณ์หรือประเภทเหตุการณ์

    ใช้เมื่อถามว่า "กี่ครั้ง" หรือ "ตัวไหนเยอะที่สุด"
    อย่าใช้เมื่อต้องการอ่านข้อความ log จริง
    """
    client = OpenSearch(hosts=[os.getenv("OPENSEARCH_URL", "http://localhost:9200")])
    response = client.search(
        index="network-logs-*",
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


def embed_batch(texts: list[str]) -> list[list[float]]:
    """เรียก embedding endpoint แบบ OpenAI-compatible

    รูปแบบเดียวกับ `scripts/embed_tickets.py` และ `scripts/ingest_docs.py`:
    ส่งคำขอ POST /embeddings แล้วตรวจว่าจำนวนมิติตรงกับ EMBEDDING_DIM ก่อนใช้งาน -
    มิฉะนั้น search_docs_semantic จะได้ vector ผิดขนาด และ knn query จะล้มเหลวโดยไม่มีการแจ้งเตือน
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


def search_docs_semantic(query: str, top_k: int = 5) -> dict:
    """ค้นหาเอกสาร runbook/นโยบายด้วยความหมาย (semantic) ไม่ใช่คำต่อคำ

    ใช้เมื่อต้องการยืนยันขั้นตอนหรือนโยบายที่เกี่ยวข้อง เช่น change window,
    มาตรฐาน MTU, ขั้นตอนการ escalate - โดยเฉพาะก่อนสรุปว่า log ผิดปกติคือเหตุ
    ขัดข้องจริง ควรตรวจนโยบายที่เกี่ยวข้องก่อนเสมอ
    อย่าใช้เพื่อนับจำนวนหรือดูแนวโน้มตัวเลขเหตุการณ์ - ให้ใช้ count_log_events แทน
    """
    vector = embed_batch([query])[0]          # รูปแบบเดียวกับ scripts/ingest_docs.py:32-53
    client = OpenSearch(hosts=[os.getenv("OPENSEARCH_URL", "http://localhost:9200")])
    response = client.search(
        index=OPENSEARCH_DOC_INDEX,
        body={"size": top_k,
              "query": {"knn": {"embedding": {"vector": vector, "k": top_k}}}},
    )
    return {
        "count": len(response["hits"]["hits"]),
        "hits": [
            {"title": h["_source"]["title"],
             "source_type": h["_source"].get("source_type"),
             "content": h["_source"]["content"][:500],
             "score": h["_score"]}
            for h in response["hits"]["hits"]
        ],
    }


def export_report(title: str, rows: list[dict], format: str = "markdown") -> dict:
    """แปลงข้อมูลเป็นไฟล์รายงาน (markdown, csv)

    ใช้เมื่อต้องการไฟล์ที่ส่งต่อให้คนอื่นได้
    """
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


def send_notification(subject: str, body: str, to: str | None = None,
                      attachment: str | None = None) -> dict:
    """ส่งอีเมลแจ้งเตือน (ไปที่ MailHog ไม่ออกนอกเครื่อง)

    ใช้เป็นขั้นตอนสุดท้ายเมื่อผู้ใช้ขอให้ส่งผลให้ทีม
    """
    to = to or os.getenv("NOTIFY_TO", "noc@example.local")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = "agent@nt.local"
    message["To"] = to
    message.set_content(body)

    if attachment and Path(attachment).exists():
        data = Path(attachment).read_bytes()
        message.add_attachment(data, maintype="text", subtype="plain",
                               filename=Path(attachment).name)

    with smtplib.SMTP(os.getenv("SMTP_HOST", "localhost"),
                      int(os.getenv("SMTP_PORT", "1025")), timeout=10) as smtp:
        smtp.send_message(message)
    return {"ok": True, "to": to, "inspect_at": "http://localhost:8025"}


TOOLS = {
    "search_tickets": search_tickets,
    "get_upstream_devices": get_upstream_devices,
    "count_log_events": count_log_events,
    "search_docs_semantic": search_docs_semantic,
    "export_report": export_report,
    "send_notification": send_notification,
}


# ==========================================================================
# 2. ReAct decision schema
# ==========================================================================

class ReactDecision(BaseModel):
    thought: str = Field(description="รู้อะไรแล้วบ้าง และจะทำอะไรต่อ พูดสั้นๆ ประโยคเดียว")
    tool: str | None = Field(
        default=None, description="เครื่องมือที่จะเรียกต่อไป หรือ null ถ้าพร้อมตอบแล้ว"
    )
    arguments: dict = Field(default_factory=dict)


# ==========================================================================
# 3. LLM client
# ==========================================================================

async def call_llm(messages: list[dict], schema: type[BaseModel] | None = None,
                   temperature: float = 0.0, max_tokens: int = 2000) -> str:
    payload: dict = {"model": LLM_MODEL, "messages": messages,
                     "temperature": temperature, "max_tokens": max_tokens}
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__,
                            "schema": schema.model_json_schema()},
        }
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{LLM_BASE_URL.rstrip('/')}/chat/completions", json=payload,
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
        )

        if response.status_code != 200:
            print(f"\n🚨 [LLM API ERROR]: {response.text}\n")

        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"] or ""


REACT_PROMPT = """\
ตอบเป้าหมายของผู้ใช้ด้วยการเรียกเครื่องมือทีละขั้น
บนทุกรอบ ให้ตัดสินใจ "ขั้นต่อไปขั้นเดียว":
- เรียกเครื่องมือหนึ่งตัวเพื่อหาข้อมูลเพิ่ม หรือ
- ตั้ง tool เป็น null เมื่อมีหลักฐานพอจะตอบแล้ว

กติกา:
1. ใช้ขั้นตอนน้อยที่สุดที่ทำงานสำเร็จ ดูผลลัพธ์ที่มีอยู่แล้วก่อนตัดสินใจ
2. ถ้าเครื่องมือก่อนหน้าล้มเหลว ข้อผิดพลาดจะอยู่ใน observation - แก้เฉพาะจุดที่ผิด
   อย่าเรียกซ้ำด้วย argument เดิม
3. ถ้าผู้ใช้ขอให้ส่งผลให้ทีม ต้องเรียก export_report ก่อน send_notification เสมอ
   (แนบไฟล์จาก path ที่ export_report คืนมาใน attachment)

ความรู้ที่ต้องใช้:
- ถ้าลูกค้าหลายรายที่อยู่คนละอุปกรณ์แจ้งอาการเดียวกัน
  ให้หา upstream ร่วมด้วย get_upstream_devices ก่อนสรุป
- ก่อนสรุปว่า log ระดับ critical จำนวนมากคือเหตุขัดข้องจริง ให้ตรวจสอบ ticket ประเภท
  maintenance ในช่วงเวลาเดียวกันก่อนเสมอ (search_tickets) และค้นนโยบายที่เกี่ยวข้อง
  ด้วย search_docs_semantic เพื่อยืนยันขั้นตอนที่ถูกต้อง

เครื่องมือที่มี:
{catalogue}
"""


TOOL_KEY_ALIASES = ("tool", "action", "action_name", "function", "name")
ARGS_KEY_ALIASES = ("arguments", "args", "action_input", "parameters", "input")


def _parse_json(schema: type[BaseModel], raw: str) -> BaseModel:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.lstrip().startswith("json") else text
    text = text.strip()

    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Not even valid JSON - let model_validate_json raise its own error.
        return schema.model_validate_json(text)

    if schema is ReactDecision and isinstance(obj, dict):
        # response_format=json_schema is a hint, not a guarantee: this
        # gateway does not always guided-decode it, and the model then falls
        # back to a "action"/"args" convention instead of this schema's
        # "tool"/"arguments". Because both fields have defaults, a plain
        # model_validate_json silently accepts that as tool=None - which
        # reads as "ready to answer" when the model actually meant to call a
        # tool. Remap the common aliases before validating so that intent
        # survives instead of getting silently swallowed.
        if not obj.get("tool"):
            for key in TOOL_KEY_ALIASES:
                if obj.get(key):
                    obj["tool"] = obj[key]
                    break
        if not obj.get("arguments"):
            for key in ARGS_KEY_ALIASES:
                if isinstance(obj.get(key), dict):
                    obj["arguments"] = obj[key]
                    break
        # Last resort: this model invents a fresh field name almost every
        # call (seen in practice: action, next_tool, action_name...) - an
        # exhaustive alias list will never keep up. A tool name is
        # unambiguous, though: it is one of a small closed set, so any exact
        # string match against a real tool name is unlikely to be a
        # coincidence and safe to treat as the intended call. Note this model
        # also sometimes fabricates a fake "tool_response"/"observation"
        # field with an invented result - that is harmless here because
        # ReactDecision has no such field, so model_validate drops it and the
        # loop always executes the real tool via call_one_tool regardless.
        if not obj.get("tool"):
            for value in obj.values():
                if isinstance(value, str) and value in TOOLS:
                    obj["tool"] = value
                    break

    return schema.model_validate(obj)


async def decide_next_step(goal: str, scratchpad: list[dict]) -> ReactDecision:
    import inspect
    catalogue = "\n\n".join(
        f"{name}{inspect.signature(fn)}: {(fn.__doc__ or '').strip()}" for name, fn in TOOLS.items()
    )
    messages = [
        {"role": "system", "content": REACT_PROMPT.format(catalogue=catalogue)},
        {"role": "user", "content": goal},
        *scratchpad,
    ]
    raw = await call_llm(messages, schema=ReactDecision)
    try:
        decision = _parse_json(ReactDecision, raw)
    except Exception as exc:  # noqa: BLE001
        # This model occasionally rambles past max_tokens before closing the
        # JSON object, which leaves no valid JSON to recover at all. That is
        # a malformed decision, not a fatal error: treat it as "stop for
        # this step" (same shape as the hallucinated-tool case below) so one
        # bad completion does not crash the whole run - the next line is
        # rare enough that failing loudly here would throw away every good
        # step already recorded in this run.
        print(f"        -> ตอบกลับจากโมเดลแปลงเป็น JSON ไม่ได้: {type(exc).__name__}")
        return ReactDecision(
            thought=f"โมเดลตอบกลับไม่ถูกต้อง (แปลง JSON ไม่ได้): {raw[:200]}",
            tool=None,
        )

    # Validate BEFORE calling. A hallucinated tool name caught here costs
    # nothing; caught at call time it costs a round trip either way, so this
    # just avoids a confusing traceback below.
    if decision.tool is not None and decision.tool not in TOOLS:
        decision = ReactDecision(
            thought=f"{decision.thought} (เครื่องมือ '{decision.tool}' ไม่มีจริง)",
            tool=None,
        )
    return decision


# ==========================================================================
# 4. Loop guard
# ==========================================================================

class LoopGuard:
    """Three independent stop conditions.

    Any one alone is defeatable:
      - a step budget alone lets a tight retry loop burn all 8 steps
      - blocking identical calls alone lets the model fuzz arguments forever
      - a per-tool cap alone lets two tools ping-pong
    Together they bound every loop shape seen in practice.
    """

    def __init__(self) -> None:
        self.total = 0
        self.signatures: dict[str, int] = {}
        self.tool_counts: dict[str, int] = {}

    def check(self, tool: str, arguments: dict) -> str | None:
        self.total += 1
        if self.total > MAX_STEPS:
            return f"เกิน {MAX_STEPS} ขั้นตอน"

        signature = f"{tool}:{json.dumps(arguments, sort_keys=True, default=str)}"
        self.signatures[signature] = self.signatures.get(signature, 0) + 1
        if self.signatures[signature] > 1:
            return f"เรียก {tool} ด้วย argument เดิมซ้ำ"

        self.tool_counts[tool] = self.tool_counts.get(tool, 0) + 1
        if self.tool_counts[tool] > MAX_SAME_TOOL:
            return f"เรียก {tool} เกิน {MAX_SAME_TOOL} ครั้ง"
        return None


# ==========================================================================
# 5. Tool execution + scratchpad
# ==========================================================================

async def call_one_tool(tool: str, arguments: dict) -> dict:
    started = time.time()
    try:
        # Tools are synchronous; run them off the event loop so the process
        # is not blocked while a DB or HTTP call is in flight.
        result = await asyncio.to_thread(TOOLS[tool], **arguments)
        elapsed = int((time.time() - started) * 1000)
        print(f"        -> สำเร็จ {elapsed} ms")
        return {"ok": True, "tool": tool, "result": result}
    except Exception as exc:  # noqa: BLE001
        print(f"        -> ล้มเหลว: {type(exc).__name__}: {exc}")
        return {"ok": False, "tool": tool, "error": f"{type(exc).__name__}: {exc}"}


def _observation_text(outcome: dict) -> str:
    if outcome["ok"]:
        return json.dumps(outcome["result"], ensure_ascii=False, default=str)[:4000]
    return f"ERROR: {outcome['error']}"


def append_turn(scratchpad: list[dict], decision: ReactDecision, outcome: dict) -> None:
    """Add one Thought/Action/Observation turn - this, not an explicit
    dependency graph, is what lets a later step use an earlier one's result:
    the model just reads it back out of the conversation."""
    scratchpad.append({
        "role": "assistant",
        "content": json.dumps(
            {"thought": decision.thought, "tool": decision.tool,
             "arguments": decision.arguments},
            ensure_ascii=False,
        ),
    })
    scratchpad.append({"role": "user", "content": f"Observation: {_observation_text(outcome)}"})


# ==========================================================================
# 6. Synthesizer
# ==========================================================================

SYNTH_PROMPT = """\
สรุปผลเป็นภาษาไทยสำหรับวิศวกรโครงข่าย

กติกา:
- ตอบคำถามที่ถูกถามก่อน ไม่ต้องเริ่มด้วยการเล่าว่าทำอะไรไปบ้าง
- อ้างอิงแหล่งที่มาของทุกข้อสรุป ระบุชื่อระบบและค่าจริงจากหลักฐาน เช่น
  "(PostgreSQL: ticket TK-25-00012)" - รูปแบบเท่านั้นที่ให้เลียนแบบ ตัวเลข
  TK-25-00012 เป็นแค่ตัวอย่างการเขียน ไม่ใช่ค่าจริง ห้ามคัดลอกไปใช้เด็ดขาด
  ต้องแทนที่ด้วยหมายเลข ticket ที่อยู่ในหลักฐานจริงเท่านั้น
- ถ้าขั้นตอนไหนล้มเหลว ให้ระบุอย่างชัดเจน ไม่ใช่นิ่งเงียบ
- ใช้เฉพาะข้อมูลในหลักฐาน ห้ามเติมสิ่งที่ไม่มี
- ถ้าหลักฐานว่างเปล่า (ไม่มีการเรียกเครื่องมือสำเร็จเลยแม้แต่ครั้งเดียว) ห้ามอ้างอิง
  หมายเลข ticket, ชื่ออุปกรณ์ หรือตัวเลขใดๆ ทั้งสิ้น ต้องระบุอย่างชัดเจนว่ายังไม่ได้ตรวจสอบข้อมูลจริง
  และไม่สามารถสรุปได้
"""


async def synthesize(goal: str, results: list[dict]) -> str:
    evidence = json.dumps(
        [{"step": i + 1, **r} for i, r in enumerate(results)],
        ensure_ascii=False, default=str,
    )[:10000]
    return await call_llm(
        [
            {"role": "system", "content": SYNTH_PROMPT},
            {"role": "system", "content": f"หลักฐาน:\n{evidence}"},
            {"role": "user", "content": goal},
        ],
        temperature=0.3,
    )


# ==========================================================================
# 7. Trace logging
# ==========================================================================

def _slugify(text: str, max_len: int = 40) -> str:
    ascii_ish = re.sub(r"[^a-zA-Z0-9ก-๙]+", "-", text.strip())
    return ascii_ish.strip("-")[:max_len].lower() or "goal"


def _write_trace(goal: str, steps: list[dict], answer: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(BANGKOK).strftime("%Y%m%d-%H%M%S")
    path = OUTPUT_DIR / f"trace-{_slugify(goal)}-{stamp}.json"
    path.write_text(
        json.dumps(
            {"goal": goal, "steps": steps, "final_answer": answer,
             "generated_at": datetime.now(BANGKOK).isoformat()},
            ensure_ascii=False, indent=2, default=str,
        ),
        encoding="utf-8",
    )
    return path


# ==========================================================================
# 8. Loop, wired up with Intent Gate (Module 7) + Memory (Module 8)
# ==========================================================================

async def run_turn(session_id: str, goal: str) -> str:
    """One conversational turn: Intent Gate -> memory context -> ReAct loop
    -> synthesis -> trace file. Calling this repeatedly with the same
    session_id is what lets a short follow-up be answered from context
    instead of starting the investigation over."""
    print(f"\n{'=' * 68}\n  [{session_id}] เป้าหมาย: {goal}\n{'=' * 68}\n")
    started = time.time()

    session = agent_memory.get(session_id)
    session.turn += 1

    # --- Intent Gate (Module 7): decide BEFORE any tool ever runs --------
    decision = await intent.classify(goal, history=session.build_context())
    if decision.label in ("out_of_scope", "needs_clarification"):
        print(f"  [Intent Gate] ปฏิเสธ ({decision.label}): {decision.reason}")
        return f"[ปฏิเสธ] {decision.reason}"
    print(f"  [Intent Gate] ผ่าน ({decision.label}, decided_by={decision.decided_by})")

    # --- Memory (Module 8): topic-shift detection + context carry-over ---
    changed, why = session.detect_topic_shift(goal)
    if changed:
        await session.start_topic(goal)
        print(f"  [Memory] เปลี่ยนหัวข้อ: {why}")
    else:
        print(f"  [Memory] {why}")
    session.add_turn("user", goal)

    # Context from earlier turns is prepended to the scratchpad; the ReAct
    # loop below appends its own Thought/Action/Observation turns onto this
    # same local list, but nothing from inside the loop is written back into
    # session memory - only the final answer is (see the end of this
    # function). That keeps conversation memory readable in natural language
    # instead of filling up with tool-call JSON.
    scratchpad: list[dict] = list(session.build_context())

    guard = LoopGuard()
    results: list[dict] = []
    steps: list[dict] = []

    print("  [ReAct loop]")
    for step_num in range(1, MAX_STEPS + 1):
        step_decision = await decide_next_step(goal, scratchpad)
        print(f"    {step_num}. คิด: {step_decision.thought}")

        if step_decision.tool is None:
            break

        blocked = guard.check(step_decision.tool, step_decision.arguments)
        if blocked:
            print(f"       หยุด: {blocked}")
            outcome = {"ok": False, "tool": step_decision.tool, "error": blocked}
        else:
            print(f"       เรียก {step_decision.tool}"
                  f"({json.dumps(step_decision.arguments, ensure_ascii=False)[:70]})")
            outcome = await call_one_tool(step_decision.tool, step_decision.arguments)

        append_turn(scratchpad, step_decision, outcome)
        results.append(outcome)
        steps.append({
            "step": step_num,
            "thought": step_decision.thought,
            "tool": step_decision.tool,
            "arguments": step_decision.arguments,
            "observation": _observation_text(outcome),
            "ok": outcome["ok"],
        })

    print("\n  [สรุป]")
    # Guard by code, not just by prompt: if not one tool call ever ran, there
    # is nothing for the model to cite - skip the LLM call entirely rather
    # than risk it inventing a ticket/device id from a habit or a stray
    # example. A prompt rule alone did not stop this in practice.
    if not results:
        answer = "ยังไม่ได้เรียกเครื่องมือใดเลย จึงไม่มีหลักฐานให้สรุปคำตอบ"
    else:
        answer = await synthesize(goal, results)
    print(f"\n{answer}\n")

    ok = sum(1 for r in results if r["ok"])
    print(f"  {'-' * 66}")
    print(f"  {ok}/{len(results)} เครื่องมือสำเร็จ · "
          f"ใช้เวลารวม {time.time() - started:.1f} วินาที")
    if any(r["tool"] == "send_notification" and r["ok"] for r in results):
        print("  ตรวจอีเมลที่ http://localhost:8025")

    session.add_turn("assistant", answer)

    trace_path = _write_trace(goal, steps, answer)
    print(f"  trace: {trace_path}\n")

    return answer


DEFAULT_GOAL = ("หา ticket ที่ยังไม่ปิดของสัปดาห์นี้ "
                "ทำรายงานสรุป แล้วส่งเมลให้ทีม NOC")


if __name__ == "__main__":
    asyncio.run(run_turn("cli", sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GOAL))
