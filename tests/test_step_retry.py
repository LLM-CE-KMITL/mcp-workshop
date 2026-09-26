"""Self-correction after a failed tool call, without a separate repair step.

Plan-then-Execute needed a dedicated repair-and-retry-once mechanism because a
step's arguments were fixed at planning time. ReAct does not: a failed call's
error becomes the next observation, and the model is free to try a corrected
argument on its very next turn like any other decision. These tests pin down
that the loop actually feeds the error back, that the model's fix is used, and
that LoopGuard still applies to the corrected call.
"""

from __future__ import annotations

import pytest
from agent import react
from agent.events import EventType
from schemas import ReactDecision


class FakeClient:
    """Fails once on a bad `range`, then succeeds once it is corrected."""

    def __init__(self):
        self.calls: list[dict] = []

    async def list_tools(self) -> list[dict]:
        return [{
            "name": "search_tickets",
            "description": "Search tickets",
            "input_schema": {"properties": {"range": {"type": "string"}}},
        }]

    async def read_resource(self, uri: str) -> str:
        return "2026-01-01T00:00:00Z"

    async def call_tool(self, name: str, arguments: dict):
        self.calls.append(dict(arguments))
        if arguments.get("range") == "last_2w":
            return {"error": "Unknown range 'last_2w'. Use one of: last_7d, last_14d"}
        return {"tickets": [{"ticket_id": "TK-1"}]}


def _decisions(*decisions: ReactDecision):
    it = iter(decisions)

    async def fake_complete_structured(messages, schema, stats=None, model=None):
        return next(it)

    return fake_complete_structured


@pytest.mark.asyncio
async def test_model_corrects_its_own_arguments_after_seeing_the_error(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(react.mcp_client, "get", lambda: fake)
    monkeypatch.setattr(react.llm, "complete_structured", _decisions(
        ReactDecision(thought="ค้นล่าสุด", tool="search_tickets",
                      arguments={"range": "last_2w"}),
        ReactDecision(thought="range ผิด ลองใหม่", tool="search_tickets",
                      arguments={"range": "last_14d"}),
        ReactDecision(thought="พอแล้ว", tool=None),
    ))

    events = [e async for e in react.run("มี ticket อะไรบ้าง")]
    types = [e[0] for e in events]

    assert types.count(EventType.THOUGHT) == 3
    results = [p for t, p in events if t == EventType.STEP_RESULT]
    assert results[0]["ok"] is False
    assert results[1]["ok"] is True
    assert fake.calls == [{"range": "last_2w"}, {"range": "last_14d"}]


@pytest.mark.asyncio
async def test_loop_guard_still_blocks_identical_repeat_after_a_failure(monkeypatch):
    """Self-correction is not a free pass: repeating the same bad call is still caught."""
    fake = FakeClient()
    monkeypatch.setattr(react.mcp_client, "get", lambda: fake)
    monkeypatch.setattr(react.llm, "complete_structured", _decisions(
        ReactDecision(thought="ค้นล่าสุด", tool="search_tickets",
                      arguments={"range": "last_2w"}),
        ReactDecision(thought="ลองอีกที", tool="search_tickets",
                      arguments={"range": "last_2w"}),
        ReactDecision(thought="หยุดดีกว่า", tool=None),
    ))

    events = [e async for e in react.run("มี ticket อะไรบ้าง")]
    results = [p for t, p in events if t == EventType.STEP_RESULT]

    assert results[0]["ok"] is False
    assert results[1]["skipped_reason"] is not None and "ซ้ำ" in results[1]["skipped_reason"]
    assert fake.calls == [{"range": "last_2w"}]
