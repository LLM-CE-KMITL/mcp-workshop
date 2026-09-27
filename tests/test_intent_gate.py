"""Intent gate.

The fast-path tests need nothing running - that is deliberate. The cheap
deterministic layer should be testable and correct on its own, before any
model is involved.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from agent.intent import fast_path, refusal_message
from conftest import needs_llm
from schemas import IntentLabel

ROOT = Path(__file__).resolve().parents[1]


def _load_gate_cases() -> list[tuple[str, str, str]]:
    """(qid, question, expected intent) for every L0 + L5 question.

    Read directly from the yaml at collection time (not through the
    session-scoped `questions` fixture) so pytest.mark.parametrize can build
    one visible test id per question - `uv run pytest tests/test_intent_gate.py -v`
    then covers the full L0-out-of-scope.yaml + L5-ambiguous.yaml sets on its
    own, with no live agent-api needed.
    """
    cases = []
    for fname in ("L0-out-of-scope.yaml", "L5-ambiguous.yaml"):
        data = yaml.safe_load(
            (ROOT / "data" / "questions" / fname).read_text(encoding="utf-8")
        )
        for q in data["questions"]:
            cases.append((q["id"], q["question"], q["expect"]["intent"]))
    return cases


GATE_CASES = _load_gate_cases()


class TestFastPath:
    @pytest.mark.parametrize("message", [
        "สถานะของ APE-NBI-03 เป็นยังไง",
        "ticket TK-25-00003 มีรายละเอียดอะไร",
        "PE-BKK-02 มีปัญหาอะไร",
    ])
    def test_identifier_means_in_scope(self, message):
        """An explicit device or ticket id is unambiguous evidence."""
        result = fast_path(message)
        assert result is not None
        assert result.label == IntentLabel.IN_SCOPE

    @pytest.mark.parametrize("message", [
        "วันนี้อากาศเป็นยังไง",
        "ช่วยเขียนอีเมลลาพักร้อนให้หน่อย",
        "หุ้น NT น่าซื้อไหม",
    ])
    def test_off_domain_refused(self, message):
        result = fast_path(message)
        assert result is not None
        assert result.label == IntentLabel.OUT_OF_SCOPE

    def test_mixed_signal_is_not_refused(self):
        """A domain question with an incidental off-domain word must survive.

        'ส่งรายงาน log ให้ทีมก่อนไปกินข้าว' is a real request. A gate that
        refuses it because of the word for lunch is worse than no gate.
        """
        result = fast_path("ส่งรายงาน log ของอุปกรณ์ให้ทีมก่อนไปกินข้าว")
        assert result is None or result.label != IntentLabel.OUT_OF_SCOPE

    @pytest.mark.parametrize("message", [
        "ticket ที่ยังไม่ปิดของอุปกรณ์ตัวไหนบ้าง",
        "log ของ interface ที่ down มีอะไรบ้าง",
    ])
    def test_multiple_domain_terms_means_in_scope(self, message):
        result = fast_path(message)
        assert result is not None and result.label == IntentLabel.IN_SCOPE

    def test_vague_reference_asks_for_clarification(self):
        result = fast_path("ดูให้หน่อยว่าปกติไหม")
        assert result is not None
        assert result.label == IntentLabel.NEEDS_CLARIFICATION


class TestRefusalMessage:
    def test_refusal_states_scope_and_gives_an_example(self):
        from schemas import IntentResult

        text = refusal_message(IntentResult(
            label=IntentLabel.OUT_OF_SCOPE, confidence=0.9, reason="test"
        ))
        assert "โครงข่าย" in text
        assert "ticket" in text, "a refusal must show what CAN be asked"

    def test_clarification_lists_what_is_missing(self):
        from schemas import IntentResult

        text = refusal_message(IntentResult(
            label=IntentLabel.NEEDS_CLARIFICATION, confidence=0.8, reason="test",
            missing_information=["ชื่ออุปกรณ์"],
        ))
        assert "ชื่ออุปกรณ์" in text


@needs_llm
class TestClassifier:
    @pytest.mark.parametrize(
        "qid,question,expected", GATE_CASES, ids=[c[0] for c in GATE_CASES]
    )
    async def test_full_gate_question_set(self, qid, question, expected, capsys):
        """Every L0 + L5 question, through the real two-layer gate.

        fast_path() runs first exactly like production does; only the
        questions it cannot decide fall through to the model. So this one
        test file, on its own, exercises the full behaviour of both files
        without needing agent-api running - `make eval`'s EVAL_LEVELS=L0,L5
        is for checking the live system end-to-end instead, a different
        thing from this.
        """
        from agent import intent

        result = fast_path(question)
        if result is None:
            result = await intent.classify(question)

        ok = result.label.value == expected
        with capsys.disabled():
            mark = "✓" if ok else "X"
            print(f"\n  {qid}   {question[:40]}")
            print(f"        [{mark}] expected {expected}, got "
                  f"{result.label.value} (conf {result.confidence:.2f})")
            print(f"        เหตุผล: {result.reason}")

        assert ok
