"""Stage 0 "Assessments into questions": one split call per assessment, then code checks."""
import json
import re
import sqlite3
from typing import Literal

from pydantic import BaseModel

from noodles.llm import LUNA, Run

SPLIT_V = "split-v1"
QType = Literal["mcq", "true_false", "short", "numeric", "open", "code"]
FORMATS = ("take_home", "online_quiz", "invigilated_exam")


class SplitQuestion(BaseModel):
    question_id: str
    text: str
    options: list[str] | None
    type: QType
    marking_material: str | None


class QuestionSplit(BaseModel):
    questions: list[SplitQuestion]
    unmatched_marking_material: list[str]


PROMPT = """You split an assessment paper and its answers into question records.
- One record per question; each sub-part (1a, 1b) is its own record.
- question_id: the label as printed on the paper, e.g. "1a" or "7".
- text: the question text copied exactly from the paper, without the label or the options.
- options: the answer options for multiple choice (without their letters), otherwise null.
- type: "mcq", "true_false", "short", "numeric", "open" (essay or long answer) or "code" (writing or tracing code).
- marking_material: that question's part of the answers, copied as is (answer, model answer, rubric or marks), or null if there is none.
- unmatched_marking_material: any part of the answers that belongs to no question.
Copy text exactly; do not rewrite, solve or add anything."""


def question_id(aid: str, label: str) -> str:
    """'Question 1(a)' in assessment 'midterm' -> 'midterm-q1a'."""
    core = re.sub(r"^(question|q)\s*", "", label.strip().lower())
    return f"{aid}-q{re.sub(r'[^a-z0-9]+', '', core) or 'x'}"


async def split(run: Run, aid: str, paper: str, answers: str | None) -> None:
    body = f"PAPER:\n{paper}\n\nANSWERS:\n{answers if answers else '(no answers provided)'}"
    out = await run.call("split", LUNA, SPLIT_V, [{"role": "system", "content": PROMPT},
                                                  {"role": "user", "content": body}], QuestionSplit)
    qs, seen = [], set()
    for q in out.questions:
        qid, base, i = question_id(aid, q.question_id), question_id(aid, q.question_id), 2
        while qid in seen:
            qid, i = f"{base}-{i}", i + 1
        seen.add(qid)
        qs.append({**q.model_dump(), "question_id": qid})
    run.write({"type": "split", "assessment_id": aid, "questions": qs,
               "unmatched_marking_material": out.unmatched_marking_material})


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def flags(paper: str, q: dict) -> list[str]:
    """Code checks: text verbatim in the paper (line breaks and spacing ignored); marking material present."""
    out = []
    if squash(q["text"]) not in squash(paper):
        out.append("Question text not found in the paper")
    if not (q.get("marking_material") or "").strip():
        out.append("Has no marking material")
    return out


def confirmed_questions(conn: sqlite3.Connection, vid: str, aid: str) -> list[dict]:
    rows = conn.execute("SELECT question_id, text, options, type, marking_material FROM questions "
                        "WHERE version_id = ? AND assessment_id = ? ORDER BY rowid", (vid, aid)).fetchall()
    return [{**dict(r), "options": json.loads(r["options"]) if r["options"] else None} for r in rows]


class QuestionsError(Exception):
    pass


def save_questions(conn: sqlite3.Connection, vid: str, aid: str, questions: list[SplitQuestion]) -> None:
    ids = [q.question_id for q in questions]
    if len(set(ids)) != len(ids):
        raise QuestionsError("two questions have the same ID")
    if bad := [i for i in ids if not i.startswith(f"{aid}-")]:
        raise QuestionsError(f"question IDs must start with {aid}-: {', '.join(bad)}")
    clash = conn.execute(f"SELECT question_id FROM questions WHERE version_id = ? AND assessment_id != ? "
                         f"AND question_id IN ({','.join('?' * len(ids))})", (vid, aid, *ids)).fetchall()
    if clash:
        raise QuestionsError(f"IDs already used by another assessment: {', '.join(r[0] for r in clash)}")
    with conn:
        conn.execute("DELETE FROM questions WHERE version_id = ? AND assessment_id = ?", (vid, aid))
        conn.executemany(
            "INSERT INTO questions (version_id, question_id, assessment_id, text, options, type, marking_material) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(vid, q.question_id, aid, q.text, json.dumps(q.options) if q.options is not None else None, q.type,
              q.marking_material if (q.marking_material or "").strip() else None) for q in questions])
