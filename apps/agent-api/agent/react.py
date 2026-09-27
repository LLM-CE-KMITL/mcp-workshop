"""Answer a question with a ReAct loop: Thought -> Action -> Observation.

There is no plan produced up front. On every iteration the model sees the
question and every observation gathered so far, then decides the single next
move - call one more tool, or answer now. This trades the up-front
inspectability of a plan for the ability to adapt mid-question: a tool result
the model did not expect (an empty list, an unexpected device id) can change
what it decides to do next, because the "next step" is decided after seeing
it rather than before.

Responsibilities:
  - ask the model for one Thought/Action at a time
  - run the chosen tool and feed the observation back into the next prompt
  - stop the agent from running forever

Loop protection is not a nicety here - it is the ONLY thing standing between
the model and an unbounded loop, because unlike a plan there is nothing to
validate before execution starts. A model that keeps calling the same tool
because a result keeps coming back "not found" is stopped by LoopGuard below,
not by anything decided in advance.

There is no separate repair-and-retry step. When a tool call fails, the error
becomes the next observation, and the model corrects its own arguments on the
next iteration like any other adjustment - that adaptability is the point of
ReAct, not a workaround bolted onto it.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import AsyncIterator

from schemas import ReactDecision, StepResult

from . import llm, mcp_client
from .events import EventType

MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "8"))
MAX_SAME_TOOL_CALLS = int(os.getenv("AGENT_MAX_SAME_TOOL_CALLS", "3"))
STEP_TIMEOUT_SECONDS = float(os.getenv("AGENT_STEP_TIMEOUT_SECONDS", "45"))

SYSTEM_PROMPT = """\
You answer questions about an IP-MPLS network using the tools listed below,
one step at a time. On every turn, decide the SINGLE next action:

- Call one tool to gather more evidence, or
- Set "tool" to null once you have enough evidence to answer the question.

Rules:

1. Call the fewest tools that fully answer the question. Do not call a tool
   to collect information the answer will not use.

2. Look at the observations you already have before deciding. If the last
   result already answers the question, stop calling tools.

3. Time ranges are relative names only: last_1h, last_6h, last_24h, last_3d,
   last_7d, last_14d, last_30d, last_90d. Never write a date.

4. If a tool call failed OR was refused as a duplicate, that exact call is now
   a dead end. Do not repeat it - change which device or arguments you use, or
   stop and answer with whatever evidence you already have. An observation
   that repeats "เรียก ... ด้วย argument เดิมซ้ำ" means you already tried this;
   producing the identical action again wastes a step and gets refused again.

5. When your MOST RECENT successful tool call was get_device_neighbors or
   get_upstream_devices, that call's whole purpose was to move the
   investigation onward to the device it returned. A bare follow-up right
   after it ("แล้วมี log ผิดปกติไหม", "log เป็นยังไงบ้าง", "เป็นยังไงบ้าง") means
   the NEWLY FOUND device, not the one you started from - even though, read on
   its own, the sentence sounds like it means "this device's own logs". Do not
   re-check the device you already checked before that step; check the one the
   step just returned instead.

Domain knowledge you are expected to apply:

- When several customers on DIFFERENT access devices report the same symptom,
  the cause is usually a shared upstream device. Find the devices from the
  tickets, then call get_upstream_devices on all of them together, then check
  that device's logs for the same period. Do not stop at the tickets.

- Logs show symptoms; configuration shows causes. An adjacency problem needs
  the configuration of BOTH ends, and the far end may be at another site.

- Severe logs may be planned maintenance. If a question is about whether
  something is an incident, check tickets with category "maintenance" covering
  the same window before concluding anything.

- The network has exactly ten devices across BKK and NBI. If the question names
  something outside that, call list_devices so the answer can say plainly that
  it does not exist.
"""


class LoopGuard:
    """Three independent stop conditions.

    Any one of them alone can be defeated; together they bound every loop shape
    seen in practice:
      - total step budget       stops slow divergence
      - repeated identical call  stops the tight retry loop
      - repeated tool regardless of arguments stops argument-fuzzing loops
    """

    def __init__(self) -> None:
        self.total_steps = 0
        self.call_signatures: dict[str, int] = {}
        self.tool_counts: dict[str, int] = {}

    def check(self, tool: str, arguments: dict) -> str | None:
        """Return a refusal reason, or None if the call may proceed."""
        self.total_steps += 1
        if self.total_steps > MAX_STEPS:
            return f"เกินจำนวนขั้นตอนสูงสุด ({MAX_STEPS} ขั้น)"

        signature = f"{tool}:{sorted(arguments.items())!r}"
        self.call_signatures[signature] = self.call_signatures.get(signature, 0) + 1
        if self.call_signatures[signature] > 1:
            return f"เรียก {tool} ด้วย argument เดิมซ้ำ"

        self.tool_counts[tool] = self.tool_counts.get(tool, 0) + 1
        if self.tool_counts[tool] > MAX_SAME_TOOL_CALLS:
            return f"เรียก {tool} เกิน {MAX_SAME_TOOL_CALLS} ครั้งในคำถามเดียว"

        return None


def _tool_catalogue(tools: list[dict]) -> str:
    return "\n\n".join(
        f"### {tool['name']}\n{tool['description'].strip()}\n"
        f"arguments: {json.dumps(tool['input_schema'].get('properties', {}), ensure_ascii=False)}"
        for tool in tools
    )


def _scratchpad(results: list[StepResult]) -> list[dict]:
    """Render prior thought/action/observation turns as chat messages.

    This - not an explicit dependency graph - is what lets a later step use an
    earlier one's result: the observation is just in the conversation, and the
    model reads it the way it reads anything else.
    """
    turns: list[dict] = []
    for result in results:
        turns.append({
            "role": "assistant",
            "content": json.dumps(
                {"thought": result.thought, "tool": result.tool, "arguments": None},
                ensure_ascii=False,
            ),
        })
        if result.ok:
            observation = json.dumps(result.result, ensure_ascii=False, default=str)[:4000]
        else:
            observation = f"ERROR: {result.error or result.skipped_reason}"
        turns.append({"role": "user", "content": f"Observation: {observation}"})
    return turns


async def run(
    question: str,
    context: list[dict] | None = None,
    stats: "llm.LLMStats | None" = None,
    model: str | None = None,
) -> AsyncIterator[tuple[EventType, dict]]:
    """Run the ReAct loop for one question, yielding events as it goes.

    Mirrors the old planner+executor pair's event shape (step_started,
    step_result) so the API layer and the UI do not need to know which
    architecture produced them - only `thought` is new, replacing the single
    upfront `plan_created`.
    """
    client = mcp_client.get()
    tools = await client.list_tools()
    clock_info = await client.read_resource("clock://now")
    guard = LoopGuard()
    results: list[StepResult] = []

    base_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Available tools:\n\n{_tool_catalogue(tools)}"},
        {"role": "system", "content": f"Current time context:\n{clock_info}"},
    ]
    if context:
        # `context` is memory.build_context(): archived-summary system
        # messages first, then the recent conversational turns. Slicing the
        # whole list with [-6:] can drop the summaries once `recent` grows
        # past a handful of turns - exactly when they matter most, since
        # that is what lets the model answer from a prior topic without
        # re-running tools. Keep every system message and only cap the
        # conversational tail.
        summaries = [turn for turn in context if turn["role"] == "system"]
        recent_turns = [turn for turn in context if turn["role"] != "system"]
        base_messages.append({
            "role": "system",
            "content": "Conversation so far:\n" + "\n".join(
                f"{turn['role']}: {turn['content'][:400]}"
                for turn in summaries + recent_turns[-6:]
            ),
        })
    base_messages.append({"role": "user", "content": question})

    async def call_tool(tool: str, step_num: int, arguments: dict) -> StepResult:
        started = time.time()
        try:
            result = await asyncio.wait_for(
                client.call_tool(tool, arguments),
                timeout=STEP_TIMEOUT_SECONDS,
            )
            elapsed = int((time.time() - started) * 1000)
            if isinstance(result, dict) and "error" in result:
                return StepResult(step=step_num, tool=tool, ok=False,
                                  duration_ms=elapsed, error=str(result["error"]))
            return StepResult(step=step_num, tool=tool, ok=True,
                              duration_ms=elapsed, result=result)
        except asyncio.TimeoutError:
            return StepResult(
                step=step_num, tool=tool, ok=False,
                duration_ms=int(STEP_TIMEOUT_SECONDS * 1000),
                error=f"หมดเวลา ({STEP_TIMEOUT_SECONDS} วินาที)",
            )
        except Exception as exc:  # noqa: BLE001
            return StepResult(step=step_num, tool=tool, ok=False,
                              duration_ms=int((time.time() - started) * 1000),
                              error=f"{type(exc).__name__}: {exc}")

    step_num = 0
    while True:
        step_num += 1
        decision = await llm.complete_structured(
            base_messages + _scratchpad(results), ReactDecision,
            stats=stats, model=model,
        )
        yield EventType.THOUGHT, {"step": step_num, "thought": decision.thought,
                                  "tool": decision.tool}

        # Guided decoding occasionally emits the literal string "null" instead
        # of JSON null for this field - `str | None` accepts both, and a
        # naive `not decision.tool` treats "null" as a truthy tool name,
        # sending it straight into call_tool() where it fails as an unknown
        # tool. That wastes a step every time it happens and, worse, can burn
        # through the whole loop budget before the model ever gets to answer.
        if not decision.tool or decision.tool.strip().lower() == "null":
            break

        refusal = guard.check(decision.tool, decision.arguments)
        if refusal:
            blocked = StepResult(step=step_num, tool=decision.tool,
                                 thought=decision.thought, ok=False,
                                 duration_ms=0, skipped_reason=refusal)
            results.append(blocked)
            yield EventType.STEP_RESULT, blocked.model_dump()
            if guard.total_steps > MAX_STEPS:
                break
            continue

        yield EventType.STEP_STARTED, {
            "step": step_num, "tool": decision.tool, "purpose": decision.thought,
            "arguments": decision.arguments,
        }
        result = await call_tool(decision.tool, step_num, decision.arguments)
        result.thought = decision.thought
        results.append(result)
        yield EventType.STEP_RESULT, result.model_dump()

        if step_num >= MAX_STEPS:
            break
