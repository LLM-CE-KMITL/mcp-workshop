#!/usr/bin/env python3
"""Chainlit frontend for the agent.

Why Chainlit and not a ready-made chat UI: everything the participant builds is
a Python object, and cl.Step renders the agent's Thought -> Action -> Observation
loop directly on screen. Watching the plan appear, the tool calls fire and the
context size change is the difference between understanding an agent loop and
having read about one.

Run:
    make ui        -> http://localhost:8000
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# The welcome banner and the example questions are shared with the reference
# demo app (apps/demo-app), so the UI looks the same whichever one is running.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo-app"))

import chainlit as cl  # noqa: E402
import httpx  # noqa: E402
from elements import cost_meter, thought_view, topic_banner  # noqa: E402
from health_page import render as health_banner  # noqa: E402
from starters import DEMO_STARTERS  # noqa: E402

AGENT_API_URL = os.getenv("AGENT_API_URL", "http://localhost:8080")


@cl.set_starters
async def starters():
    return [cl.Starter(label=s["label"], message=s["message"]) for s in DEMO_STARTERS]


@cl.on_chat_start
async def start():
    cl.user_session.set("session_id", cl.user_session.get("id"))

    # Status of every dependency up front, so an audience can see the whole
    # stack is reachable before the first question is asked.
    await cl.Message(
        content=f"## ผู้ช่วยดูแลโครงข่าย IP-MPLS\n\n{health_banner()}"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    session_id = "default"  # session_id = cl.user_session.get("session_id") or "default" หากต้องการรัน ID

    answer = cl.Message(content="")
    steps: dict[int, cl.Step] = {}
    intent_step: cl.Step | None = None
    usage: dict = {}

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST",
            f"{AGENT_API_URL}/chat",
            json={"message": message.content, "session_id": session_id},
        ) as response:
            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    raw, buffer = buffer.split("\n\n", 1)
                    payload = None
                    for line in raw.splitlines():
                        if line.startswith("data: "):
                            payload = json.loads(line[6:])
                    if payload is None:
                        continue

                    event_type = payload["type"]
                    data = payload["data"]

                    # -------- intent --------
                    if event_type == "intent_checked":
                        intent_step = cl.Step(
                            name=f"ตรวจสอบขอบเขตคำถาม: {data['label']}",
                            type="tool",
                        )
                        await intent_step.__aenter__()
                        intent_step.output = (
                            f"**{data['label']}** "
                            f"(มั่นใจ {data['confidence']:.0%} · "
                            f"ตัดสินโดย {data.get('decided_by', '-')})\n\n"
                            f"{data['reason']}"
                        )
                        await intent_step.__aexit__(None, None, None)

                    # -------- topic change --------
                    elif event_type == "topic_changed":
                        await topic_banner(data)

                    # -------- ReAct thought (one per loop iteration) --------
                    elif event_type == "thought":
                        thought_step = cl.Step(
                            name=f"คิด [{data['step']}]", type="llm"
                        )
                        await thought_step.__aenter__()
                        thought_step.output = thought_view(data)
                        await thought_step.__aexit__(None, None, None)

                    # -------- tool calls --------
                    elif event_type == "step_started":
                        step = cl.Step(
                            name=f"[{data['step']}] {data['tool']}", type="tool"
                        )
                        await step.__aenter__()
                        step.input = json.dumps(
                            data.get("arguments", {}), ensure_ascii=False, indent=2
                        )
                        steps[data["step"]] = step

                    elif event_type == "step_result":
                        step = steps.get(data["step"])
                        if step:
                            if data["ok"]:
                                body = json.dumps(
                                    data["result"], ensure_ascii=False, indent=2
                                )
                                step.output = (
                                    f"สำเร็จใน {data['duration_ms']} ms\n\n"
                                    f"```json\n{body[:2500]}\n```"
                                )
                            else:
                                reason = data.get("error") or data.get("skipped_reason")
                                step.output = f"ไม่สำเร็จ: {reason}"
                            await step.__aexit__(None, None, None)

                    # -------- answer --------
                    elif event_type == "token":
                        await answer.stream_token(data)

                    # -------- grounding --------
                    elif event_type == "grounding_checked":
                        if data.get("supported") is False and data.get("unsupported_claims"):
                            warning = cl.Step(name="ตรวจสอบความถูกต้อง", type="tool")
                            await warning.__aenter__()
                            warning.output = (
                                "พบข้อความที่หลักฐานยังไม่รองรับ:\n"
                                + "\n".join(f"- {c}" for c in data["unsupported_claims"])
                            )
                            await warning.__aexit__(None, None, None)

                    elif event_type == "usage":
                        usage = data

                    elif event_type == "error":
                        await cl.Message(
                            content=f"เกิดข้อผิดพลาด: {data.get('error')}"
                        ).send()

    await answer.send()

    if usage:
        await cost_meter(usage)
