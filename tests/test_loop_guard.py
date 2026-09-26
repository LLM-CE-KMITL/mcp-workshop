"""Loop protection.

Runs without any service: the guard is pure logic, which is exactly why it can
be relied on. In the ReAct loop this is the ONLY defense against an unbounded
loop - there is no upfront plan to validate first - so these tests pin down
all three stop conditions.
"""

from __future__ import annotations

from agent.react import LoopGuard


class TestLoopGuard:
    def test_allows_normal_sequence(self):
        guard = LoopGuard()
        assert guard.check("search_tickets", {"status": "open"}) is None
        assert guard.check("get_upstream_devices", {"device_ids": ["a"]}) is None
        assert guard.check("search_logs", {"device_id": "x"}) is None

    def test_blocks_identical_repeat(self):
        """The tight retry loop: same tool, same arguments, forever."""
        guard = LoopGuard()
        assert guard.check("search_tickets", {"status": "open"}) is None
        reason = guard.check("search_tickets", {"status": "open"})
        assert reason is not None and "ซ้ำ" in reason

    def test_blocks_argument_fuzzing(self):
        """Different arguments each time still counts as a loop."""
        guard = LoopGuard()
        blocked = None
        for i in range(10):
            blocked = guard.check("search_logs", {"limit": i})
            if blocked:
                break
        assert blocked is not None

    def test_blocks_total_step_budget(self, monkeypatch):
        import agent.react as react

        monkeypatch.setattr(react, "MAX_STEPS", 3)
        monkeypatch.setattr(react, "MAX_SAME_TOOL_CALLS", 99)
        guard = react.LoopGuard()
        results = [guard.check(f"tool_{i}", {"i": i}) for i in range(5)]
        assert results[-1] is not None
