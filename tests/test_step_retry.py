"""Repair-and-retry-once when a step's arguments are wrong.

The executor does not re-plan on failure (Module 6 explains why that is
dangerous), but a bad argument value - like an invented time range - is cheap
to fix without touching the rest of the plan. These tests pin down that the
retry actually happens, happens only once, and still respects LoopGuard.
"""

from __future__ import annotations

import pytest
from agent import executor
from agent.events import EventType
from schemas import Plan, PlanStep


def _plan(arguments: dict) -> Plan:
    return Plan(
        goal="test", reasoning="test",
        steps=[PlanStep(step=1, tool="search_tickets", arguments=arguments,
                         purpose="find recent tickets")],
        expected_sources=["postgres"],
    )


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

    async def call_tool(self, name: str, arguments: dict):
        self.calls.append(dict(arguments))
        if arguments.get("range") == "last_2w":
            return {"error": "Unknown range 'last_2w'. Use one of: last_7d, last_14d"}
        return {"tickets": [{"ticket_id": "TK-1"}]}


@pytest.mark.asyncio
async def test_repairs_bad_argument_and_retries_once(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(executor.mcp_client, "get", lambda: fake)

    class FakeRepaired:
        arguments = {"range": "last_14d"}

    async def fake_complete_structured(messages, schema, stats=None, model=None):
        return FakeRepaired()

    monkeypatch.setattr(executor.llm, "complete_structured", fake_complete_structured)

    events = [e async for e in executor.execute(_plan({"range": "last_2w"}))]
    types = [e[0] for e in events]

    assert EventType.STEP_RETRY in types
    retry_payload = next(p for t, p in events if t == EventType.STEP_RETRY)
    assert retry_payload["arguments"] == {"range": "last_14d"}

    final = next(p for t, p in events if t == EventType.STEP_RESULT)
    assert final["ok"] is True
    assert fake.calls == [{"range": "last_2w"}, {"range": "last_14d"}]


@pytest.mark.asyncio
async def test_no_retry_when_repair_returns_same_arguments(monkeypatch):
    """A repair that changes nothing must not cost a second tool call."""
    fake = FakeClient()
    monkeypatch.setattr(executor.mcp_client, "get", lambda: fake)

    class FakeRepaired:
        arguments = {"range": "last_2w"}

    async def fake_complete_structured(messages, schema, stats=None, model=None):
        return FakeRepaired()

    monkeypatch.setattr(executor.llm, "complete_structured", fake_complete_structured)

    events = [e async for e in executor.execute(_plan({"range": "last_2w"}))]
    types = [e[0] for e in events]

    assert EventType.STEP_RETRY not in types
    final = next(p for t, p in events if t == EventType.STEP_RESULT)
    assert final["ok"] is False
    assert fake.calls == [{"range": "last_2w"}]

