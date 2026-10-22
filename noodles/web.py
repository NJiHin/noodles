"""Web agent, marker and AI exposure (sys-design "Web agent", "Marker", "Right and wrong", "AI exposure")."""
import re
from typing import Literal

from pydantic import BaseModel

from noodles.llm import LUNA, SOL, Run

WEB_V, MARK_V = "web-v1", "mark-v1"
Verdict = Literal["correct", "partial", "incorrect"]
WEB_SEARCH = [{"type": "web_search"}]


class WebAnswer(BaseModel):
    final_answer: str | None
    sources: list[str]


class Mark(BaseModel):
    verdict: Verdict
    reason: str


WEB_PROMPT = """Answer the exam question. Search the web as you need. Answer concisely, as in an exam.
For multiple choice, give the letter of the option. List the URLs of the sources you used."""

MARK_PROMPT = """You mark one answer to an exam question against the professor's marking material.
The marking material may be in any form (model answer, rubric, marking scheme); judge against it as it is.
Ignore phrasing, length and style; judge only whether the meaning matches the marking material.
verdict: "correct", "partial" or "incorrect". reason: one line."""


def question_text(q: dict) -> str:
    """What every agent sees: the question's context (if any), then the question and its options."""
    return (f"{q['context']}\n\n" if q["context"] else "") + q["text"] + ("".join(f"\n({chr(65 + i)}) {o}" for i, o in enumerate(q["options"])) if q["options"] else "")


async def web_agent(run: Run, q: dict) -> dict:
    """Fingerprint is the question only, so it's reused when the materials change."""
    out = await run.call("web", SOL, WEB_V, [{"role": "system", "content": WEB_PROMPT},
                                             {"role": "user", "content": question_text(q)}],
                         WebAnswer, question_id=q["question_id"], tools=WEB_SEARCH)
    return out.model_dump()


def _norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    return {"t": "true", "f": "false"}.get(s, s)


def exact_match(q: dict, given: str) -> bool:
    """Same answer as the key, where an option letter and its text count as the same answer."""
    def forms(x: str) -> set[str]:
        x, out = _norm(x), {_norm(x)}
        for i, o in enumerate(q["options"] or []):
            if x in (chr(97 + i), _norm(o)):
                out |= {chr(97 + i), _norm(o)}
        return out
    return bool(forms(given) & forms(q["marking_material"]))


async def mark(run: Run, q: dict, given: str | None) -> dict:
    """One final answer. MCQ and true/false by exact match in code; other types by the LLM marker,
    which sees the question, the marking material and this answer only."""
    if given is None:
        return {"verdict": "incorrect", "reason": "No answer given.", "by": "code"}
    if q["type"] in ("mcq", "true_false"):
        ok = exact_match(q, given)
        return {"verdict": "correct" if ok else "incorrect", "by": "code",
                "reason": "Exact match with the answer key." if ok else f"Doesn't match the answer key ({q['marking_material']})."}
    body = f"Question:\n{question_text(q)}\n\nMarking material:\n{q['marking_material']}\n\nAnswer:\n{given}"
    out = await run.call("marker", LUNA, MARK_V, [{"role": "system", "content": MARK_PROMPT},
                                                  {"role": "user", "content": body}], Mark, question_id=q["question_id"])
    return {**out.model_dump(), "by": "marker"}


EXPOSURE = {(True, True): "ai_exposed", (True, False): "course_specific",
            (False, True): "neither_taught", (False, False): "broken_or_gap"}


def exposure(marks: dict | None) -> str:
    """The AI-exposure cell; only "correct" counts as right."""
    if not marks:
        return "not_assessed"
    return EXPOSURE[marks["student"]["verdict"] == "correct", marks["web"]["verdict"] == "correct"]
