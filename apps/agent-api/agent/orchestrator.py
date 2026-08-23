"""Multi-agent routing (Module 6).

The single-planner design used by the main flow is the right default for this
dataset. This module exists to make the alternative concrete rather than
theoretical, and to let participants measure the difference themselves.

Pattern implemented: Orchestrator-Workers.

    router  decides which specialists are relevant
    workers each own one data source and one narrow skill
    merger  combines their findings

When it helps: many tools, or specialists that need different instructions.
When it hurts: this workshop's ten tools, where the coordination overhead of
extra model calls exceeds anything gained.

The comparison, not the code, is the lesson. instructions/day2/module6 has
participants run both against the same question and look at the numbers.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from . import llm


class Specialist(str, Enum):
    TICKETS = "tickets"      # PostgreSQL: what was reported
    TOPOLOGY = "topology"    # Neo4j: what connects to what
    LOGS = "logs"            # OpenSearch: what the equipment reported


class RoutingDecision(BaseModel):
    specialists: list[Specialist] = Field(
        description="Which specialists are needed. Choose the minimum."
    )
    reason: str
    sequential: bool = Field(
        description=(
            "True when a later specialist needs an earlier one's findings. "
            "False when they can work independently and be merged."
        )
    )


SPECIALIST_BRIEF = {
    Specialist.TICKETS: (
        "คุณดูแลข้อมูล ticket และการตั้งค่าอุปกรณ์ "
        "ตอบเฉพาะสิ่งที่ 'ถูกแจ้งเข้ามา' และ 'ถูกตั้งค่าไว้' "
        "ถ้าคำถามเกี่ยวกับพฤติกรรมจริงของอุปกรณ์ ให้บอกว่าเป็นหน้าที่ของ logs"
    ),
    Specialist.TOPOLOGY: (
        "คุณดูแลโครงสร้างการเชื่อมต่อ "
        "หน้าที่สำคัญที่สุดคือหาจุดร่วม upstream ของอุปกรณ์หลายตัว "
        "และจำไว้ว่า adjacency ข้ามพื้นที่ได้"
    ),
    Specialist.LOGS: (
        "คุณดูแล log ของอุปกรณ์และเอกสารปฏิบัติการ "
        "ก่อนสรุปว่าอะไรเป็นเหตุเสีย ต้องเช็คก่อนเสมอว่าเป็นงาน maintenance หรือไม่"
    ),
}

ROUTER_PROMPT = """\
Route a network operations question to the specialists that can answer it.

  tickets   trouble tickets, incident history, device configuration, circuits
  topology  physical connections, adjacencies, shared upstream devices
  logs      device syslog, event counts, health scoring, runbooks

Choose the minimum set. Set sequential=true only when one specialist genuinely
needs another's output first - for example, finding devices from tickets before
looking up what they share upstream.
"""


async def route(question: str, stats: llm.LLMStats | None = None,
                model: str | None = None) -> RoutingDecision:
    return await llm.complete_structured(
        [
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": question},
        ],
        RoutingDecision, stats=stats, model=model,
    )
