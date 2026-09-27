#!/usr/bin/env python3
"""Challenge 2 "before" baseline: run untouched.

    uv run solutions/challenges/challenge2_before.py

This is step 1 of the challenge (INSTRUCTIONS/day1/07-challenge2-schema-under-pressure.md):
"รันโมดูลของตัวเองกับทั้ง 25 ใบ" - take the Workshop 1 extractor exactly as it
came out of that workshop, with NONE of the four defences Challenge 2 asks
for, and see which of the 25 tickets it breaks on.

It reuses StructuredExtractor unmodified (no trimming, no injection check, no
circuit breaker) so the failures printed here are the actual gap Challenge 2
closes - not a strawman. `check_expectations()` is imported from the finished
solution so both runs are graded by the exact same rubric; only the
extractor under test differs.

Run this first, then challenge2_robust_extractor.py, and diff the two
"ยังไม่ผ่าน" lists - that comparison is the deliverable, not either script
alone.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "solutions" / "day1"))
sys.path.insert(0, str(ROOT / "solutions" / "challenges"))
sys.path.insert(0, str(ROOT / "apps" / "agent-api"))

from workshop1_extractor import (  # noqa: E402
    StructuredExtractor, TicketExtraction, load_conversations,
)
from challenge2_robust_extractor import check_expectations  # noqa: E402

FIXTURES = ROOT / "data" / "challenge_fixtures" / "noisy_tickets.json"


async def main() -> int:
    # ตั้งใจใช้ตัวเปล่า ไม่ใช่ RobustExtractor - นี่คือจุดที่ต่างจาก
    # challenge2_robust_extractor.py ทั้งไฟล์
    extractor = StructuredExtractor(TicketExtraction)

    noisy = json.loads(FIXTURES.read_text(encoding="utf-8"))
    normal = load_conversations(20)
    total = len(noisy) + len(normal)

    print(f"\n=== Challenge 2 · BEFORE (extractor เดิมจาก Workshop 1 ยังไม่แก้อะไร, {total} ใบ) ===\n")
    print(f"  {'id':<12}{'ok':<5}{'retry':<7}หมายเหตุ")
    print("  " + "-" * 70)

    failures: list[str] = []

    for fixture in noisy:
        result = await extractor.extract(fixture["conversation"])
        problems = check_expectations(fixture, result)
        print(f"  {fixture['id']:<12}{'yes' if result.ok else 'NO':<5}{result.attempts:<7}"
              f"{' · '.join(problems)}")
        for error in result.errors:
            print(f"               ! error: {error}")
        for problem in problems:
            failures.append(f"{fixture['id']}: {problem}")
        if not result.ok:
            failures.append(f"{fixture['id']}: สกัดไม่สำเร็จเลย")

    for ticket_id, conversation in normal:
        result = await extractor.extract(conversation)
        print(f"  {ticket_id:<12}{'yes' if result.ok else 'NO':<5}{result.attempts:<7}")
        if not result.ok:
            failures.append(f"{ticket_id}: สกัดไม่สำเร็จ")

    print("\n  " + "-" * 70)
    print(f"  ยังไม่ผ่าน {len(failures)} ข้อ จาก {total} ใบ (นี่คือ baseline - ยังไม่มีเกราะป้องกันใดๆ)")
    for failure in failures:
        print(f"    - {failure}")
    print("\n  ต่อไป: uv run solutions/challenges/challenge2_robust_extractor.py "
          "แล้วเทียบว่ารายการนี้สั้นลงตรงไหนบ้าง\n")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
