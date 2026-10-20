"""Grounding checker (sys-design "Grounding checker"): a code check, then one isolated LLM call per cited step."""
import asyncio
import sqlite3
from typing import Literal

from pydantic import BaseModel

from noodles.llm import LUNA, Run

GROUND_V = "grounding-v1"


class Grounding(BaseModel):
    verdict: Literal["supported", "partial", "unsupported"]
    reason: str


PROMPT = """You check whether passages from course materials support a claim.
- "supported": the passages state the claim or directly imply it.
- "partial": the passages cover part of the claim, or only touch on it.
- "unsupported": the passages don't support the claim.
Judge only from the passages given, not from your own knowledge. Give a one-line reason."""


def code_check(step: dict, passages: dict, target: str, n: int, prereq: str | None) -> str | None:
    """The reason a step fails the code check, or None. passages: cited ID -> row (version_id, week)."""
    if not step["evidence"]:
        return "Cites no passage."
    if missing := [e for e in step["evidence"] if e not in passages]:
        return f"Cites passages that don't exist: {', '.join(missing)}."
    rows = [passages[e] for e in step["evidence"]]
    if step["source"] == "course" and any(p["version_id"] != target or p["week"] > n for p in rows):
        return f"A course step must cite this course's passages from weeks 1 to {n}."
    if step["source"] == "prerequisite" and any(p["version_id"] != prereq for p in rows):
        return "A prerequisite step must cite the prerequisite course's passages."
    return None


async def ground(run: Run, conn: sqlite3.Connection, answer: dict, target: str, prereq: str | None) -> list[dict]:
    """Check every course/prerequisite step of one student output in parallel. Returns {step_id, verdict, reason}."""
    steps = [s for s in answer["steps"] if s["source"] in ("course", "prerequisite")]
    cited = sorted({e for s in steps for e in s["evidence"]})
    passages = {r["passage_id"]: r for r in conn.execute(
        f"SELECT passage_id, version_id, week, text FROM passages WHERE version_id IN (?, ?) "
        f"AND passage_id IN ({','.join('?' * len(cited))})", (target, prereq, *cited))}

    async def check(s):
        if why := code_check(s, passages, target, answer["week_cutoff"], prereq):
            return {"step_id": s["step_id"], "verdict": "unsupported", "reason": why}
        body = f"Claim: {s['claim']}\n\nPassages:\n" + "\n\n".join(
            f"[{e}] {passages[e]['text']}" for e in s["evidence"])
        out = await run.call("grounding", LUNA, GROUND_V, [{"role": "system", "content": PROMPT},
                                                            {"role": "user", "content": body}],
                             Grounding, question_id=answer["question_id"])
        return {"step_id": s["step_id"], **out.model_dump()}

    return list(await asyncio.gather(*(check(s) for s in steps)))
