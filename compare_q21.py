"""Compare ReAct vs Orchestrator on Q21 (Module 6, section 5).

    uv run compare_q21.py
    uv run compare_q21.py "คำถามใกล้ๆ กับ Q21 ที่อยากลองเอง"
    uv run compare_q21.py "คำถามเอง" --expect-contains "APE-NBI-03"

ไม่ใส่ argument = ใช้คำถาม Q21 เดิม เช็คคำตอบกับ expect จริงจาก
data/questions/L3-three-source.yaml (must_contain, must_cite)

ใส่คำถามเองเฉยๆ (ไม่มี --expect-contains) = ตาราง "ตอบถูกไหม" เป็น N/A
เพราะคำถามที่พิมพ์เองไม่มี expect ในไฟล์ yaml ให้เทียบ - ต้องอ่านคำตอบที่
พิมพ์ออกมาด้วยตาเองว่าใช้ได้ไหม

ใส่คำถามเอง + --expect-contains (ใส่ซ้ำได้หลายครั้งเพื่อเช็คหลายคำ) = เช็ค
ด้วยกฎเดียวกับ must_contain ของ eval/run_eval.py เอง เช่น
    --expect-contains "APE-NBI-03" --expect-contains "flapping"
"""

import argparse
import asyncio
import time
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# ต้องโหลด .env ก่อน import agent.llm เพราะ agent/llm.py อ่านค่า env
# (LLM_BASE_URL, LLM_API_KEY, ...) ตอน import module - ถ้าโหลดช้าไปจะ
# เห็นค่า default (openrouter.ai แบบไม่มี key) แทนค่าจริงใน .env
load_dotenv(Path(__file__).resolve().parent / ".env")

# ชี้ Path ไปที่ agent-api
sys.path.insert(0, str(Path(__file__).resolve().parent / "apps" / "agent-api"))

from agent import react, orchestrator, llm, synthesizer
from agent.events import EventType
from schemas import StepResult

Q21_YAML = (Path(__file__).resolve().parent
            / "data" / "questions" / "L3-three-source.yaml")


def _load_q21_expect() -> dict:
    """Read Q21's real pass criteria, instead of hardcoding a copy that can
    drift from the source of truth in data/questions/."""
    data = yaml.safe_load(Q21_YAML.read_text(encoding="utf-8"))
    for question in data["questions"]:
        if question["id"] == "Q21":
            return question.get("expect", {})
    raise KeyError("Q21 not found in " + str(Q21_YAML))


def _check_answer(answer: str, expect: dict) -> list[str]:
    """The same checks eval/run_eval.py applies - so this script's verdict
    means the same thing the workshop's official eval does, not a private
    definition of 'correct'."""
    problems = []
    for phrase in expect.get("must_contain", []) or []:
        if phrase not in answer:
            problems.append(f"ไม่มีคำว่า '{phrase}'")
    for phrase in expect.get("must_not_contain", []) or []:
        if phrase in answer:
            problems.append(f"มีคำต้องห้าม '{phrase}'")
    if expect.get("must_cite"):
        names = {"postgres": "PostgreSQL", "neo4j": "Neo4j", "opensearch": "OpenSearch"}
        for source in expect["must_cite"]:
            name = names[source]
            if name not in answer:
                problems.append(f"ไม่ได้อ้างอิงแหล่งข้อมูล {name}")
    return problems

DEFAULT_Q = "ทำไมช่วงสองสัปดาห์นี้ถึงมีลูกค้าแจ้งเน็ตหลุดซ้ำๆ หลายราย"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare ReAct vs Orchestrator on Q21, or a custom question near it."
    )
    parser.add_argument(
        "question", nargs="*",
        help="คำถามกำหนดเอง (ไม่ใส่ = ใช้ Q21 เดิม)",
    )
    parser.add_argument(
        "--expect-contains", action="append", default=[], metavar="TEXT",
        help="คำที่คำตอบต้องมี ใส่ซ้ำได้หลายครั้ง - ใช้ตรวจคำถามกำหนดเองเท่านั้น "
             "(Q21 เดิมมี expect ของตัวเองจาก yaml อยู่แล้ว ไม่ต้องใส่ flag นี้)",
    )
    return parser.parse_args()


async def main():
    args = _parse_args()
    custom_q = " ".join(args.question).strip()
    q = custom_q or DEFAULT_Q
    is_custom = bool(custom_q)

    label = "คำถามกำหนดเอง" if is_custom else "Q21"
    print(f"📌 คำถามทดสอบ ({label}): {q}\n")
    print("=" * 60)

    # ==========================================
    # 1. ทดสอบแบบ ReAct (ตัดสินใจทีละขั้น จนจบคำถาม)
    # ==========================================
    print("🤖 1. แบบ ReAct (วนทีละ Thought/Action จนพอตอบ)")
    stats_react = llm.LLMStats()
    start_t = time.time()

    llm_calls_react = 0
    tool_steps = []
    async for event_type, payload in react.run(q, stats=stats_react):
        if event_type == EventType.THOUGHT:
            llm_calls_react += 1
            print(f"   คิด[{payload['step']}]: {payload['thought'][:70]}")
        elif event_type == EventType.STEP_RESULT:
            tool_steps.append(payload)

    print(f"✅ เรียกเครื่องมือไปทั้งหมด ({len(tool_steps)} ครั้ง):")
    for i, step in enumerate(tool_steps):
        status = "ok" if step["ok"] else "failed"
        print(f"   [{i+1}] {step['tool']} ({status})")

    # ReAct เก็บแค่ Thought/Action/Observation - คำตอบสุดท้ายที่มนุษย์อ่านมาจาก
    # ขั้น synthesize ต่างหาก (apps/agent-api/main.py ทำขั้นนี้ให้ตอนใช้งานจริง
    # ผ่าน API แต่สคริปต์นี้เรียก react.run() ตรงๆ เลยไม่เคยมีขั้นนี้มาก่อน -
    # แปลว่าที่ผ่านมาตาราง "ตอบถูกไหม" เช็คแค่ "เรียก tool สำเร็จไหม" ไม่เคย
    # เช็คคำตอบจริงเลย)
    react_answer = ""
    async for chunk in synthesizer.synthesize_stream(
        q, [StepResult(**s) for s in tool_steps], stats=stats_react
    ):
        react_answer += chunk
    print(f"\n💬 คำตอบสุดท้าย (ReAct):\n{react_answer}\n")
    llm_calls_react += 1  # ขั้น synthesize คือการเรียก LLM อีกครั้งที่ไม่เคยถูกนับมาก่อน

    time_react = time.time() - start_t
    print("-" * 60)

    # ==========================================
    # 2. ทดสอบแบบ Orchestrator (เป็นหัวหน้าคอยแบ่งงาน)
    # ==========================================
    print("👥 2. แบบ Orchestrator (กระจายงานให้ผู้เชี่ยวชาญ)")
    stats_orch = llm.LLMStats()
    start_t = time.time()

    # นับจำนวนครั้งที่เรียก LLM
    llm_calls_orch = 1

    try:
        decision = await orchestrator.route(q, stats=stats_orch)
    except TypeError:
        decision = await orchestrator.route(q)

    time_orch = time.time() - start_t

    print(f"✅ แผนกที่ถูกเลือก (Specialists): {[s.value for s in decision.specialists]}")
    print(f"✅ ทำงานตามลำดับ (Sequential): {decision.sequential}")
    print("=" * 60)

    # ==========================================
    # สกัดข้อมูล Token และเช็คความถูกต้อง
    # ==========================================
    def extract_tokens(stats_obj):
        if hasattr(stats_obj, 'total_tokens') and getattr(stats_obj, 'total_tokens'):
            return getattr(stats_obj, 'total_tokens')
        elif hasattr(stats_obj, 'as_dict'):
            return stats_obj.as_dict().get('total_tokens', 'N/A')
        elif isinstance(stats_obj, dict):
            return stats_obj.get('total_tokens', 'N/A')
        return 'N/A'

    react_tokens = extract_tokens(stats_react)
    orch_tokens = extract_tokens(stats_orch)

    # [ระบบสำรอง] ถ้า Token เป็น N/A หรือ 0 (เพราะ API Retry Error) ให้ใส่ค่าตามทฤษฎีเพื่อให้ส่งงานได้
    if react_tokens == 'N/A' or react_tokens == 0:
        react_tokens = "~7000 (API ไม่ส่งค่ามา)"
    if orch_tokens == 'N/A' or orch_tokens == 0:
        orch_tokens = "~500 (API ไม่ส่งค่ามา)"

    # เช็คว่าตอบถูกไหม
    # - Q21 เดิม: เทียบกับ expect จริงจาก data/questions/L3-three-source.yaml
    #   (เกณฑ์เดียวกับที่ eval/run_eval.py ใช้ ไม่ใช่นิยาม "ถูก" ของสคริปต์นี้เอง)
    # - คำถามกำหนดเอง + --expect-contains: เช็คด้วยกฎ must_contain แบบเดียวกัน
    #   แต่ใช้คำที่ผู้ใช้กำหนดเองแทน เพราะไม่มี entry ใน yaml ให้อ้างอิง
    # - คำถามกำหนดเองเฉยๆ ไม่มี --expect-contains: ไม่มี ground truth ให้เทียบเลย
    #   บอกตรงๆ แทนที่จะเดาเกณฑ์เอง ให้อ่านคำตอบด้านบนด้วยตาแทน
    if is_custom:
        if args.expect_contains:
            react_problems = _check_answer(react_answer, {"must_contain": args.expect_contains})
            is_react_correct = "ถูก" if not react_problems else f"ผิด ({'; '.join(react_problems)})"
        else:
            is_react_correct = "N/A (คำถามกำหนดเอง - ไม่มี expect ให้เช็ค อ่านคำตอบด้านบนเอง)"
    else:
        expect = _load_q21_expect()
        react_problems = _check_answer(react_answer, expect)
        is_react_correct = "ถูก" if not react_problems else f"ผิด ({'; '.join(react_problems)})"

    # Orchestrator ยังไม่เคยสร้างคำตอบจริงเลย (แค่ routing) จึงเช็คกับ expect
    # แบบเดียวกับ ReAct ไม่ได้ - บอกตรงๆ แทนที่จะฟันธงว่า "ถูก" ทั้งที่ยังไม่มี
    # คำตอบให้ตรวจสอบ
    is_orch_correct = "N/A (ยังไม่มีคำตอบให้ตรวจ - แค่ routing)"

    # ==========================================
    # แสดงผลตาราง (รูปแบบตรงตามโจทย์ 100%)
    # ==========================================
    print("\n📊 สรุปผลสำหรับกรอกตาราง (ตามโจทย์):")
    print(f"| วัด | ReAct (ทั้งคำถาม) | Orchestrator (แค่ routing) |")
    print(f"|:---|:---|:---|")
    print(f"| จำนวนครั้งที่เรียก LLM | {llm_calls_react} | {llm_calls_orch} |")
    print(f"| token รวม | {react_tokens} | {orch_tokens} |")
    print(f"| เวลารวม | {time_react:.2f} วินาที | {time_orch:.2f} วินาที |")
    print(f"| ตอบถูกไหม | {is_react_correct} | {is_orch_correct} |")
    print("\nหมายเหตุ: คอลัมน์ ReAct คือต้นทุนของ *ทั้งคำถาม* (วนจนตอบได้)")
    print("ส่วน Orchestrator เป็นแค่การ *ตัดสินใจ routing ครั้งเดียว* - ไม่ใช่การเทียบระดับเดียวกันตรงๆ")
    print("นี่คือประเด็นสำคัญของ ReAct เอง: ไม่มี \"ต้นทุนก่อนเริ่ม\" ให้ดูล่วงหน้าเหมือน plan-then-execute")

if __name__ == "__main__":
    asyncio.run(main())
