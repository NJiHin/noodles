"""Stage 2: the student agent (topic list, lookup_concept tool loop) and the re-check of uncited steps.

Student-facing queries go through student_conn(), which can't read the assessment tables.
"""
import asyncio
import json
import re
import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from noodles import db
from noodles.coursemap import topic_label
from noodles.grounding import ground
from noodles.llm import LUNA, Run, add_usage

STUDENT_V, RECHECK_V = "student-v1", "recheck-v1"
MAX_LOOKUPS, RECHECK_HITS = 5, 3
Source = Literal["course", "prerequisite", "assumed_knowledge", "none"]
ASSESSMENT_TABLES = {"assessments", "assessment_files", "questions"}


class Step(BaseModel):
    claim: str
    source: Source
    evidence: list[str]
    reason: str | None
    accepted_id: int | None


class StudentAnswer(BaseModel):
    final_answer: str | None
    steps: list[Step]


class Relabel(BaseModel):
    step: int
    source: Source
    evidence: list[str]
    reason: str | None
    accepted_id: int | None


class Relabels(BaseModel):
    steps: list[Relabel]


def _deny_assessments(action, arg1, *_):
    return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and arg1 in ASSESSMENT_TABLES else sqlite3.SQLITE_OK


def student_conn(path: Path) -> sqlite3.Connection:
    """Connection for student-facing queries: reading an assessment table raises."""
    c = db.connect(path)
    c.set_authorizer(_deny_assessments)
    return c


# Week limit (sys-design "Course store"): the target up to week N, the prerequisite whatever its week.
LIMIT = "((p.version_id = :target AND p.week <= :n) OR p.version_id = :prereq)"


def topics(conn: sqlite3.Connection, target: str, n: int, prereq: str | None) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT c.* FROM concepts c WHERE (c.version_id = :target AND EXISTS (SELECT 1 FROM occurrences o WHERE "
        "o.version_id = c.version_id AND o.concept_id = c.concept_id AND o.week <= :n)) OR c.version_id = :prereq "
        "ORDER BY c.version_id = :target, c.concept_id", {"target": target, "n": n, "prereq": prereq}).fetchall()


def reachable(conn: sqlite3.Connection, target: str, n: int, prereq: str | None) -> list[list]:
    """Every passage within the week limit (text and heading), for the student's fingerprint."""
    return [list(r) for r in conn.execute(f"SELECT p.passage_id, p.heading, p.text FROM passages p WHERE {LIMIT} "
                                          "ORDER BY p.version_id, p.passage_id", {"target": target, "n": n, "prereq": prereq})]


def lookup(conn: sqlite3.Connection, ids: list[str], target: str, n: int, prereq: str | None) -> list[sqlite3.Row]:
    """Passages tagged with any of the topics, within the week limit."""
    names = {f"t{i}": t for i, t in enumerate(ids)}
    return conn.execute(
        "SELECT DISTINCT p.version_id, p.passage_id, p.week, p.heading, p.text FROM evidence e JOIN passages p ON "
        f"p.version_id = e.version_id AND p.passage_id = e.passage_id WHERE e.concept_id IN ({','.join(':' + k for k in names)}) "
        f"AND {LIMIT} ORDER BY p.version_id = :target, p.week, p.passage_id",
        {**names, "target": target, "n": n, "prereq": prereq}).fetchall()


def recheck_search(conn: sqlite3.Connection, claim: str, target: str, n: int, prereq: str | None) -> list[sqlite3.Row]:
    """FTS5 keyword search on a claim's words (each quoted, joined by OR, so FTS syntax in the claim is inert),
    best RECHECK_HITS by BM25, within the week limit."""
    words = re.findall(r"\w+", claim)
    if not words:
        return []
    query = " OR ".join(f'"{w}"' for w in words)
    return conn.execute(
        f"SELECT p.passage_id, p.heading, p.text FROM passages_fts JOIN passages p ON p.rowid = passages_fts.rowid "
        f"WHERE passages_fts MATCH :q AND {LIMIT} ORDER BY bm25(passages_fts) LIMIT {RECHECK_HITS}",
        {"q": query, "target": target, "n": n, "prereq": prereq}).fetchall()


def show(p) -> str:
    return f"{p['heading']}\n[{p['passage_id']}] {p['text']}"


PROMPT = """You are a student. You have completed {prereq} and attended weeks 1 to {n} of {course}. You know nothing else in this subject.

Answer the exam question concisely, as in an exam. List the steps of your answer: only steps that bring in knowledge, with pure reasoning folded into those steps' claims. For each step give its source:
- "course": you found it in a passage of {course} weeks 1 to {n}. Cite the passage IDs as evidence.
- "prerequisite": you found it in a passage of the prerequisite course. Cite the passage IDs as evidence.
- "assumed_knowledge": something implied by the course's stated entry requirements (e.g. A-level maths, or the prerequisite course) that isn't in the provided materials. Give a one-line reason. Example: "Rearranging gives n = 2k + 1." with reason "The entry requirement is A-level maths, which covers basic algebra."
- "none": subject knowledge the answer needs that you wouldn't already know and can't find in the course or prerequisite materials. Example: "Memoisation caches results." when no passage covers memoisation.
Use "prerequisite" whenever the material exists there; use "assumed_knowledge" only when it doesn't. When unsure between "assumed_knowledge" and "none", choose "none".
Cite only passage IDs you were shown. Leave evidence empty for "assumed_knowledge" and "none", and reason and accepted_id null unless stated above.
If you can't attempt the question, set final_answer to null and still list the steps you managed.

To read the materials, call lookup_concept with the IDs of the topics you need (at most {max} calls; zero is fine). It returns every passage tagged with those topics. The topics you have been taught:
{topics}"""

RECHECK = """A keyword search of the materials you can see found passages for some of your uncited steps (numbered from 1 in your answer). For each step below, return its corrected label: "course" or "prerequisite" with the passage IDs that support it, or keep it "none" or "assumed_knowledge" (with its reason) if these passages don't cover it.

"""


def tool(ids: list[str]) -> dict:
    return {"type": "function", "name": "lookup_concept", "strict": True,
            "description": "Every passage tagged with these topics, with its ID and heading.",
            "parameters": {"type": "object", "additionalProperties": False, "required": ["topic_ids"],
                           "properties": {"topic_ids": {"type": "array", "items": {"type": "string", "enum": ids}}}}}


async def student(run: Run, conn: sqlite3.Connection, q: dict, course: str, target: str, prereq: str | None,
                  prereq_course: str | None) -> dict:
    """Run the student on one question, then the re-check. Returns the student output for the question."""
    n = q["week_cutoff"]
    listed = topics(conn, target, n, prereq)
    ids = [t["concept_id"] for t in listed]
    system = PROMPT.format(prereq=prereq_course or "no prerequisite courses", n=n, course=course, max=MAX_LOOKUPS,
                           topics="\n".join(f"{t['concept_id']} | {topic_label(t['name'], json.loads(t['aliases']))} | "
                                            f"{t['description'] or ''}" for t in listed) or "(none)")
    question = q["text"] + ("".join(f"\n({chr(65 + i)}) {o}" for i, o in enumerate(q["options"])) if q["options"] else "")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]

    async def loop():
        convo, usage, lookups = list(messages), {}, 0
        while True:
            out, u = await run.request("student", LUNA, convo, StudentAnswer,
                                       [tool(ids)] if ids and lookups < MAX_LOOKUPS else None)
            usage = add_usage(usage, u)
            if not isinstance(out, list):
                return out.model_dump(), usage, {"conversation": convo + [{"role": "assistant", "content": out.model_dump_json()}],
                                                 "lookups": lookups}
            for call in out:
                lookups += 1
                convo.append(call)
                convo.append({"type": "function_call_output", "call_id": call["call_id"],
                              "output": tool_output(conn, call, ids, lookups, target, n, prereq)})

    rec = await run.cached("student", LUNA, STUDENT_V, [messages, ids, reachable(conn, target, n, prereq)],
                           q["question_id"], loop)
    answer = StudentAnswer.model_validate(rec["output"])
    steps = [s.model_dump() for s in answer.steps]
    found = {i: hits for i, s in enumerate(steps, 1) if s["source"] in ("none", "assumed_knowledge")
             and (hits := recheck_search(conn, s["claim"], target, n, prereq))}
    if found:
        body = RECHECK + "\n\n".join(f"Step {i}: {steps[i - 1]['claim']}\n" + "\n".join(show(h) for h in hits)
                                     for i, hits in found.items())
        fixed = await run.call("recheck", LUNA, RECHECK_V, rec["conversation"] + [{"role": "user", "content": body}],
                               Relabels, question_id=q["question_id"])
        for r in fixed.steps:
            if r.step in found:
                steps[r.step - 1].update(r.model_dump(exclude={"step"}))
    return {"question_id": q["question_id"], "week_cutoff": n, "final_answer": answer.final_answer,
            "steps": [{"step_id": f"{q['question_id']}-s{i}", **s} for i, s in enumerate(steps, 1)]}


def tool_output(conn, call: dict, ids: list[str], lookups: int, target: str, n: int, prereq: str | None) -> str:
    if lookups > MAX_LOOKUPS:
        return f"Refused: the limit is {MAX_LOOKUPS} lookups per question. Answer with what you have."
    try:
        asked = json.loads(call["arguments"])["topic_ids"]
    except (ValueError, KeyError, TypeError):
        return "Rejected: arguments must be {\"topic_ids\": [...]}."
    if bad := [i for i in asked if i not in ids]:
        return f"Rejected: {', '.join(map(str, bad))} is not a listed topic ID."
    return "\n\n".join(show(p) for p in lookup(conn, asked, target, n, prereq)) or "No passages."


async def test_drive(run: Run, db_path: Path, course: str, target: str, prereq: str | None, prereq_course: str | None,
                     questions: list[dict]) -> None:
    """Every question in parallel: student, re-check, grounding. Each result is written to the run log."""
    conn = student_conn(db_path)
    try:
        async def one(q):
            answer = await student(run, conn, q, course, target, prereq, prereq_course)
            checks = await ground(run, conn, answer, target, prereq)
            run.write({"type": "answer", **answer, "grounding": checks})
        await asyncio.gather(*(one(q) for q in questions))
    finally:
        conn.close()
