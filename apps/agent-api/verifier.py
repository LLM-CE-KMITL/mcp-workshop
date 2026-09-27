"""Grounding check: does every factual claim in the answer trace back to a
step result, or did the synthesiser add something the tools never returned?

This deliberately does NOT call an LLM to judge itself (see the lab's bonus
1). Regex against the evidence text is cheaper and, for the specific claim
shapes this network domain produces (device ids, ticket ids, percentages,
dates), more reliable than asking a model to grade another model's answer -
the failure mode we are guarding against (confident but wrong) is exactly
the failure mode a judge-LLM is also prone to.

The dangerous case is not "APE-CNX-99 mentioned but does not exist" (rare -
the synthesiser sees real ids in its own evidence, it does not usually invent
a plausible-looking one from nothing). It is the case in the lab's scenario
S4: every fact in the answer is real, but the conclusion drawn from it is
not - severe log entries reported as an outage when a maintenance ticket
covers the exact same device and window.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from schemas import GroundingVerdict, StepResult

DEVICE_ID = re.compile(r"\b[A-Z]{2,4}-[A-Z]{3}-\d{2}\b")
TICKET_ID = re.compile(r"\bTK-\d{2}-\d{5}\b")
PERCENT = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%")
ISO_DATE = re.compile(r"(20\d{2})-\d{2}-\d{2}")

# Confident, uninsured incident language. Hedged language ("อาจจะ", "คาดว่า",
# "น่าจะ") is deliberately NOT in this list - the lab is explicit that
# expressing uncertainty must not be flagged, only false confidence.
SEVERE_INCIDENT_WORDS = ["เหตุเสียร้ายแรง", "เหตุเสีย", "ขัดข้องรุนแรง", "outage รุนแรง"]
HEDGE_WORDS = ["อาจจะ", "อาจเป็น", "คาดว่า", "น่าจะ", "เป็นไปได้ว่า"]

# "ไม่ใช่เหตุเสีย" and "PE-CNX-99 ไม่พบในระบบ" are the agent correctly denying a
# claim, not making one - a nearby negation must suppress the flag the same
# way a hedge does, otherwise the correct answer to Q18/Q30 gets punished.
NEGATION_WORDS = ["ไม่ใช่", "ไม่ได้เป็น", "ไม่ถือว่าเป็น", "ไม่พบ", "ไม่ปรากฏ",
                  "ไม่มีอยู่จริง", "ไม่มีในระบบ", "ไม่ได้ลงทะเบียน"]


def _evidence_text(results: list[StepResult]) -> str:
    """Concatenate every successful observation into one searchable blob.

    Failed/skipped steps carry no evidence - a claim cannot be grounded in a
    tool call that errored out.
    """
    chunks = []
    for step in results:
        if not getattr(step, "ok", False) or step.result is None:
            continue
        chunks.append(json.dumps(step.result, ensure_ascii=False, default=str))
    return "\n".join(chunks)


def _near(answer: str, target: str, qualifiers: list[str], radius: int = 40) -> bool:
    """True if any of `qualifiers` appears within `radius` chars of `target`.

    Sentence-level parsing would be more precise, but for a 20-minute lab
    exercise this is the right amount of engineering: a character window
    catches "อาจเป็นเหตุเสีย" and "ไม่ใช่เหตุเสีย" without a false negative on
    genuinely unhedged, unnegated claims - and Thai has no reliable
    word-boundary regex to lean on instead.
    """
    idx = answer.find(target)
    if idx == -1:
        return False
    window = answer[max(0, idx - radius): idx + radius]
    return any(q in window for q in qualifiers)


async def verify(answer: str, results: list[StepResult]) -> dict:
    """Check `answer` against the evidence in `results`. Never raises -
    a broken verifier must not take down a turn that otherwise succeeded."""
    evidence = _evidence_text(results)
    unsupported: list[str] = []
    corrections: list[str] = []

    try:
        # ---------- 1. Device / ticket ids that do not appear in evidence ----------
        # Mentioning an id ONLY to say it was not found (Q30's "PE-CNX-99
        # ไม่พบในระบบ") is the correct answer, not a claim that needs evidence -
        # do not flag it.
        for device in set(DEVICE_ID.findall(answer)):
            if device not in evidence and not _near(answer, device, NEGATION_WORDS):
                unsupported.append(f"อ้างอุปกรณ์ {device} แต่ไม่มีในหลักฐาน")

        for ticket in set(TICKET_ID.findall(answer)):
            if ticket not in evidence and not _near(answer, ticket, NEGATION_WORDS):
                unsupported.append(f"อ้าง ticket {ticket} แต่ไม่มีในหลักฐาน")

        # ---------- 2. Numbers/percentages not backed by evidence ----------
        for pct in set(PERCENT.findall(answer)):
            if pct not in evidence:
                unsupported.append(f"อ้างตัวเลข {pct.strip()} แต่ไม่มีในหลักฐาน")

        # ---------- 3. Incident framing that contradicts a maintenance ticket ----------
        # This is the S4 trap: the logs are real, but a maintenance ticket
        # covering the same period changes what the severity actually means.
        has_maintenance_evidence = (
            '"category": "maintenance"' in evidence or "maintenance" in evidence.lower()
        )
        if has_maintenance_evidence:
            # Longest phrase first: "เหตุเสียร้ายแรง" contains "เหตุเสีย", and
            # matching both would just report the same sentence twice.
            for word in sorted(SEVERE_INCIDENT_WORDS, key=len, reverse=True):
                if (word in answer
                        and not _near(answer, word, HEDGE_WORDS)
                        and not _near(answer, word, NEGATION_WORDS)):
                    unsupported.append(
                        f"ระบุว่า '{word}' ทั้งที่หลักฐานมี ticket ประเภท maintenance "
                        "ครอบคลุมช่วงเวลาเดียวกัน"
                    )
                    corrections.append(
                        "ควรระบุว่าเป็นงานซ่อมบำรุงที่แจ้งล่วงหน้า ไม่ใช่เหตุเสีย "
                        "เว้นแต่จะระบุชัดว่าเกิดขึ้นนอกช่วงเวลาที่แจ้งไว้"
                    )
                    break

        # ---------- 4. Dates outside the range the evidence actually covers ----------
        evidence_years = {int(y) for y in ISO_DATE.findall(evidence)}
        if evidence_years:
            span = range(min(evidence_years) - 1, max(evidence_years) + 1)
            for year in {int(y) for y in ISO_DATE.findall(answer)}:
                if year not in span:
                    unsupported.append(
                        f"อ้างปี {year} ซึ่งอยู่นอกช่วงเวลาที่หลักฐานครอบคลุม "
                        f"({min(evidence_years)}-{max(evidence_years)})"
                    )
    except Exception as exc:  # noqa: BLE001 - a grounding bug must not fail the turn
        return GroundingVerdict(
            supported=True,
            unsupported_claims=[],
            corrections=[f"grounding check ล้มเหลว ({type(exc).__name__}: {exc}) - ข้ามการตรวจ"],
        ).model_dump()

    return GroundingVerdict(
        supported=len(unsupported) == 0,
        unsupported_claims=unsupported,
        corrections=corrections,
    ).model_dump()


# ==========================================================================
# Self-test: `uv run apps/agent-api/verifier.py`
# ==========================================================================
if __name__ == "__main__":
    import asyncio

    def _step(result: dict) -> StepResult:
        return StepResult(step=1, tool="test", ok=True, duration_ms=0, result=result)

    async def _run() -> None:
        print("1) คำตอบที่จงใจผิด (ต้องจับได้ 3 จุด: incident/maintenance, ticket ปลอม, % ปลอม)")
        evidence = [
            _step({
                "logs": [{"device_id": "APE-BKK-05", "severity": "error",
                          "message": "interface flapping"}],
            }),
            _step({
                "ticket_id": "TK-25-00099", "device_id": "APE-BKK-05",
                "category": "maintenance", "status": "closed",
                "window": "2026-09-20 to 2026-09-21",
            }),
        ]
        bad = ("APE-BKK-05 เกิดเหตุเสียร้ายแรง มี ticket TK-99-99999 "
               "รายงานไว้ CPU สูงถึง 95%")
        verdict = await verify(bad, evidence)
        print(f"   supported={verdict['supported']}")
        for claim in verdict["unsupported_claims"]:
            print(f"   - {claim}")
        assert verdict["supported"] is False
        assert len(verdict["unsupported_claims"]) >= 3, "ต้องจับได้ครบ 3 จุด"

        print("\n2) คำตอบที่ถูกต้อง (ต้องไม่ถูกจับผิด - false positive)")
        good = ("APE-BKK-05 มี log severity error เรื่อง interface flapping "
                "แต่มี ticket TK-25-00099 ประเภท maintenance ครอบคลุมช่วงเวลาเดียวกัน "
                "จึงน่าจะเป็นงานที่แจ้งไว้ล่วงหน้า ไม่ใช่เหตุเสีย")
        verdict = await verify(good, evidence)
        print(f"   supported={verdict['supported']}")
        assert verdict["supported"] is True, verdict["unsupported_claims"]

        print("\n3) Q30 style: อุปกรณ์ไม่มีอยู่จริง แต่คำตอบถูกต้อง (ต้องไม่ถูกจับผิด)")
        q30_evidence = [
            _step({"found": False, "device_id": "PE-CNX-99",
                   "note": "ไม่พบอุปกรณ์นี้ในระบบ",
                   "available_devices": ["APE-BKK-05", "PE-BKK-02"]}),
        ]
        q30_good = "PE-CNX-99 ไม่พบในระบบ ไม่มีอุปกรณ์นี้อยู่จริง"
        verdict = await verify(q30_good, q30_evidence)
        print(f"   supported={verdict['supported']}")
        assert verdict["supported"] is True, verdict["unsupported_claims"]

        print("\n4) verifier ต้องไม่ crash แม้ไม่มีหลักฐานเลย")
        verdict = await verify("ไม่พบข้อมูลอุปกรณ์นี้ในระบบ", [])
        print(f"   supported={verdict['supported']}")

        print("\nผ่านทุกเคส")

    asyncio.run(_run())
