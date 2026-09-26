#!/usr/bin/env python3
"""Workshop 2 reference solution: a ReAct agent loop written from scratch.

    python solutions/day2/workshop2_agent.py
    python solutions/day2/workshop2_agent.py "หา ticket ที่ยังไม่ปิด แล้วส่งสรุปให้ NOC"

No agent framework, and deliberately no MCP either - tools are plain Python
functions called directly. Day 3 replaces that layer with MCP and nothing else
about the loop changes, which is the point: the loop is the part worth
understanding, and it is about 200 lines.

This is a ReAct loop, not a plan-then-execute one: there is no upfront Plan
object. On every iteration the model sees the goal and every observation so
far, and decides the single next action - call one tool, or stop and answer.
That is also why there is no separate "repair the arguments" step: a failed
call's error just becomes the next observation, and the model corrects itself
on its next turn like any other decision.

Capabilities required by the curriculum: search, convert a file, send email.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from enum import Enum
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv
from neo4j import GraphDatabase
from opensearchpy import OpenSearch
from pydantic import BaseModel, Field

# Loaded before reading any env var below - running this script directly with
# `uv run` (not through docker compose --env-file) never sees .env otherwise.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

BANGKOK = timezone(timedelta(hours=7))
PG_DSN = os.getenv("PG_DSN",
                   "postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3-30b-a3b")
OUTPUT_DIR = Path("data/reports")

MAX_STEPS = 8
MAX_SAME_TOOL = 3


# ==========================================================================
# 1. Tools
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
                   temperature: float = 0.0) -> str:
    payload: dict = {"model": LLM_MODEL, "messages": messages,
                     "temperature": temperature, "max_tokens": 1500}
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

เครื่องมือที่มี:
{catalogue}
"""


def _parse_json(schema: type[BaseModel], raw: str) -> BaseModel:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.lstrip().startswith("json") else text
    return schema.model_validate_json(text.strip())


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
    decision = _parse_json(ReactDecision, raw)

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
    if outcome["ok"]:
        observation = json.dumps(outcome["result"], ensure_ascii=False, default=str)[:4000]
    else:
        observation = f"ERROR: {outcome['error']}"
    scratchpad.append({"role": "user", "content": f"Observation: {observation}"})


# ==========================================================================
# 6. Synthesizer
# ==========================================================================

SYNTH_PROMPT = """\
สรุปผลเป็นภาษาไทยสำหรับวิศวกรโครงข่าย

กติกา:
- ตอบคำถามที่ถูกถามก่อน ไม่ต้องเริ่มด้วยการเล่าว่าทำอะไรไปบ้าง
- อ้างอิงแหล่งที่มาของทุกข้อสรุป เช่น (PostgreSQL: ticket TK-25-00001)
- ถ้าขั้นตอนไหนล้มเหลว ให้บอกตรงๆ ไม่ใช่เงียบไป
- ใช้เฉพาะข้อมูลในหลักฐาน ห้ามเติมสิ่งที่ไม่มี
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
# 7. Loop
# ==========================================================================

async def run(goal: str) -> None:
    print(f"\n{'=' * 68}\n  เป้าหมาย: {goal}\n{'=' * 68}\n")
    started = time.time()

    guard = LoopGuard()
    scratchpad: list[dict] = []
    results: list[dict] = []

    print("  [ReAct loop]")
    for step_num in range(1, MAX_STEPS + 1):
        decision = await decide_next_step(goal, scratchpad)
        print(f"    {step_num}. คิด: {decision.thought}")

        if decision.tool is None:
            break

        blocked = guard.check(decision.tool, decision.arguments)
        if blocked:
            print(f"       หยุด: {blocked}")
            outcome = {"ok": False, "tool": decision.tool, "error": blocked}
        else:
            print(f"       เรียก {decision.tool}"
                  f"({json.dumps(decision.arguments, ensure_ascii=False)[:70]})")
            outcome = await call_one_tool(decision.tool, decision.arguments)

        append_turn(scratchpad, decision, outcome)
        results.append(outcome)

    print("\n  [สรุป]")
    answer = await synthesize(goal, results)
    print(f"\n{answer}\n")

    ok = sum(1 for r in results if r["ok"])
    print(f"  {'-' * 66}")
    print(f"  {ok}/{len(results)} เครื่องมือสำเร็จ · "
          f"ใช้เวลารวม {time.time() - started:.1f} วินาที")
    if any(r["tool"] == "send_notification" and r["ok"] for r in results):
        print("  ตรวจอีเมลที่ http://localhost:8025")
    print()


DEFAULT_GOAL = ("หา ticket ที่ยังไม่ปิดของสัปดาห์นี้ "
                "ทำรายงานสรุป แล้วส่งเมลให้ทีม NOC")


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GOAL))
