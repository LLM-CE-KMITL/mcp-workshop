"""Grounding check - v0 baseline: run untouched, then fix the bugs yourself.

    uv run apps/agent-api/verifier-v0.py

This is step 1 of the lab (INSTRUCTIONS/day2/09-lab-grounding-verification.md):
a first, honest attempt at `verify(answer, results)` that looks reasonable on
a skim but has real bugs. It is what a first draft of this function tends to
look like before anyone runs it against evidence shaped like what `react.py`
actually produces.

Run the self-test below and read the output carefully - it will not crash,
which is exactly the trap. Some of the checks the lab requires silently do
nothing at all, and at least one flags a CORRECT answer as wrong. Find those,
fix them here, then compare against the answer key: `apps/agent-api/verifier.py`.
Same self-test shape in both files, on purpose - so the diff in results *is*
the list of bugs.
"""

import re
from typing import List, Dict, Any


async def verify(answer: str, results: list) -> Dict[str, Any]:
    """
    ตรวจสอบว่าทุกข้ออ้างในคำตอบ (answer) มีหลักฐานจาก step results รองรับหรือไม่
    """
    supported_tickets = set()
    supported_devices = set()
    evidence_text = ""

    for step in results:
        text_content = getattr(step, "result_text", str(step))
        evidence_text += " " + text_content

        found_tickets = re.findall(r"TK-\d{2}-\d{5}", text_content)
        supported_tickets.update(found_tickets)

        found_devices = re.findall(r"[A-Z]{3}-[A-Z]{3}-\d{2}", text_content)
        supported_devices.update(found_devices)

    errors = []

    # 1. ตรวจสอบ Ticket ID
    mentioned_tickets = re.findall(r"TK-\d{2}-\d{5}", answer)
    for ticket in mentioned_tickets:
        if not supported_tickets or ticket not in supported_tickets:
            errors.append(f"พบ Ticket ที่ไม่มีในหลักฐาน: {ticket}")

    # 2. ตรวจสอบ Metrics / ตัวเลขเปอร์เซ็นต์
    percent_matches = re.findall(r"\d+%", answer)
    if "CPU" in answer or percent_matches:
        if "CPU" not in evidence_text and not any(m in evidence_text for m in percent_matches):
            errors.append("มีการอ้างอิงข้อมูล Metrics หรือเปอร์เซ็นต์ที่ไม่มีอยู่ในหลักฐาน")

    # 3. ตรวจสอบการบิดเบือนเหตุการณ์
    if "เหตุเสีย" in answer or "ร้ายแรง" in answer:
        if "maintenance" in evidence_text.lower() or "ซ่อมบำรุง" in evidence_text:
            if "เหตุเสีย" not in evidence_text and "เสีย" not in evidence_text:
                errors.append("บิดเบือนข้อเท็จจริง: ระบุว่าเป็นเหตุเสีย แต่หลักฐานระบุเป็น Maintenance")
        elif not evidence_text:
            errors.append("อ้างอิงเหตุเสียโดยไม่มีหลักฐานสนับสนุน")

    # Field names match schemas.GroundingVerdict (supported / unsupported_claims
    # / corrections) - main.py's grounding_checked event expects this shape,
    # not whatever a verifier invents on its own.
    return {
        "supported": len(errors) == 0,
        "unsupported_claims": errors,
        "corrections": [],
    }


# ==========================================================================
# Self-test - SAME fixtures/questions as apps/agent-api/verifier.py, so the
# two runs are graded by the exact same cases. Read the actual output; do
# not assume it worked just because nothing raised.
# ==========================================================================
if __name__ == "__main__":
    import asyncio
    from schemas import StepResult

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
        for e in verdict["unsupported_claims"]:
            print(f"   - {e}")

        print("\n2) คำตอบที่ถูกต้อง (ต้องไม่ถูกจับผิด - false positive)")
        good = ("APE-BKK-05 มี log severity error เรื่อง interface flapping "
                "แต่มี ticket TK-25-00099 ประเภท maintenance ครอบคลุมช่วงเวลาเดียวกัน "
                "จึงน่าจะเป็นงานที่แจ้งไว้ล่วงหน้า ไม่ใช่เหตุเสีย")
        verdict = await verify(good, evidence)
        print(f"   supported={verdict['supported']}")
        for e in verdict["unsupported_claims"]:
            print(f"   - {e}")

        print("\n3) Q30 style: อุปกรณ์ไม่มีอยู่จริง แต่คำตอบถูกต้อง (ต้องไม่ถูกจับผิด)")
        q30_evidence = [
            _step({"found": False, "device_id": "PE-CNX-99",
                   "note": "ไม่พบอุปกรณ์นี้ในระบบ",
                   "available_devices": ["APE-BKK-05", "PE-BKK-02"]}),
        ]
        q30_good = "PE-CNX-99 ไม่พบในระบบ ไม่มีอุปกรณ์นี้อยู่จริง"
        verdict = await verify(q30_good, q30_evidence)
        print(f"   supported={verdict['supported']}")
        for e in verdict["unsupported_claims"]:
            print(f"   - {e}")

        print("\n4) verifier ต้องไม่ crash แม้ไม่มีหลักฐานเลย")
        verdict = await verify("ไม่พบข้อมูลอุปกรณ์นี้ในระบบ", [])
        print(f"   supported={verdict['supported']}")

        print("\nจบการทดสอบ - เทียบผลลัพธ์ทั้ง 4 ข้อกับ apps/agent-api/verifier.py")
        print("แล้วดูว่าข้อไหนต่างกัน และทำไม")

    asyncio.run(_run())
