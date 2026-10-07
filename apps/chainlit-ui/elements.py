"""Custom UI elements.

The token and cost meter is not decoration. On a local model there is no
per-token price, so the meaningful cost is GPU time - latency, throughput and
how much context is being carried into every call. Putting those numbers on
screen for three days changes how participants write prompts far more
effectively than a slide about it does.
"""

from __future__ import annotations

import chainlit as cl


def thought_view(data: dict) -> str:
    """Render one ReAct Thought.

    There is no plan to diagram: the agent decides a single next action - or
    decides it is ready to answer - and this is that one decision made visible.
    """
    if data.get("tool"):
        return f"{data['thought']}\n\n**ขั้นต่อไป**: เรียก `{data['tool']}`"
    return f"{data['thought']}\n\n**พร้อมตอบแล้ว** ไม่เรียกเครื่องมือเพิ่ม"


async def topic_banner(data: dict) -> None:
    """Announce a topic change and show the context actually shrinking.

    This is the visible proof that memory management is doing something. Without
    it, participants have to take the mechanism on faith.
    """
    before = data.get("context_tokens_before", 0)
    after = data.get("context_tokens_after", 0)
    saved = before - after

    body = [
        "### เปลี่ยนหัวข้อการสนทนา",
        "",
        f"**เหตุผล**: {data.get('reason')}",
        "",
        f"ขนาด context: `{before}` → `{after}` tokens"
        + (f"  (**ลดลง {saved}**)" if saved > 0 else ""),
    ]
    if data.get("archived_summaries"):
        body += ["", "**สรุปเรื่องเดิมที่เก็บไว้แทน detail ทั้งหมด**:"]
        body += [f"- {s}" for s in data["archived_summaries"]]

    await cl.Message(content="\n".join(body), author="ระบบความจำ").send()


async def cost_meter(usage: dict) -> None:
    """Show what the turn actually cost in GPU terms, on a single line.

    A table of eight rows is tall in Chainlit and pushes the answer off screen,
    while the audience only needs a glance: how long, how many tokens, how many
    model and tool calls.
    """
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", 0)
    seconds = usage.get("latency_ms", 0) / 1000

    summary = (
        f"⏱ **{seconds:.1f} วินาที** · "
        f"🔤 **{total:,}** token (เข้า {prompt:,} / ออก {completion:,}) · "
        f"🧠 LLM **{usage.get('llm_calls', 0)}** ครั้ง · "
        f"🔧 tool **{usage.get('tool_calls', 0)}** ครั้ง · "
        f"⚡ {usage.get('tokens_per_second', 0):.1f} token/วินาที · "
        f"📏 context {usage.get('context_tokens', 0):,}"
    )

    note = ""
    context_tokens = usage.get("context_tokens", 0)
    if context_tokens > 4000:
        note = (
            "\n\n> context เริ่มใหญ่แล้ว ถ้าเปลี่ยนเรื่องระบบจะสรุปแล้วตัดทิ้งให้อัตโนมัติ"
        )

    await cl.Message(
        content=f"{summary}{note}",
        author="มาตรวัดต้นทุน",
    ).send()
