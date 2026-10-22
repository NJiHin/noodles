"""Stage 0 "Assessments into questions": one split call per assessment, then code checks."""
import json
import re
import sqlite3
from typing import Literal

from pydantic import BaseModel

from noodles.llm import LUNA, Run

SPLIT_V = "split-v2"
QType = Literal["mcq", "true_false", "short", "numeric", "open", "code"]
FORMATS = ("take_home", "online_quiz", "invigilated_exam")


class SplitQuestion(BaseModel):
    question_id: str
    context: str | None = None  # scenario, data or formulas the question needs, copied per question
    text: str
    options: list[str] | None
    type: QType
    marking_material: str | None


class SplitRecord(SplitQuestion):
    question_id: str | None  # the number printed on the paper, or None: code numbers it by position


class QuestionSplit(BaseModel):
    questions: list[SplitRecord]
    unmatched_marking_material: list[str]


PROMPT = """You split an assessment paper and its answers into question records.
- One record per question; each sub-part (1a, 1b) is its own record.
- question_id: the question number as printed on the paper, e.g. "1a" or "7"; null if the paper prints no number for it.
- context: text the question needs that is not part of the question itself, such as a scenario, a data table or formulas shared by several questions, copied exactly into every question it applies to; null if none.
- text: the question text copied exactly from the paper, without the number, the context or the options.
- options: the answer options for multiple choice (without their letters), otherwise null.
- type: "mcq", "true_false", "short", "numeric", "open" (essay or long answer) or "code" (writing or tracing code).
- marking_material: that question's part of the answers, copied as is (answer, model answer, rubric or marks), or null if there is none.
- unmatched_marking_material: any part of the answers that belongs to no question.
Copy text exactly; do not rewrite, solve or add anything."""


NUMBER = re.compile(r"^(question|q)?\s*\d+\s*(\(?[a-z]\)?|\.\d+|\(?[ivx]+\)?)?$")  # 7, 1a, Q3, Question 2(b), 2.1, 3(ii)


def question_id(aid: str, label: str | None, position: int) -> str:
    """'Question 1(a)' in assessment 'midterm' -> 'midterm-q1a'. A label that isn't a question number
    (None, or e.g. 'S_x' when the paper prints none) gives the question's position instead: 'midterm-q3'."""
    label = (label or "").strip().lower()
    if not NUMBER.match(label):
        return f"{aid}-q{position}"
    return f"{aid}-q{re.sub(r'[^a-z0-9]+', '', re.sub(r'^(question|q)', '', label))}"


async def split(run: Run, aid: str, paper: str, answers: str | None) -> None:
    body = f"PAPER:\n{paper}\n\nANSWERS:\n{answers if answers else '(no answers provided)'}"
    out = await run.call("split", LUNA, SPLIT_V, [{"role": "system", "content": PROMPT},
                                                  {"role": "user", "content": body}], QuestionSplit)
    qs, seen = [], set()
    for pos, q in enumerate(out.questions, 1):
        qid, base, i = question_id(aid, q.question_id, pos), question_id(aid, q.question_id, pos), 2
        while qid in seen:
            qid, i = f"{base}-{i}", i + 1
        seen.add(qid)
        qs.append({**q.model_dump(), "question_id": qid})
    run.write({"type": "split", "assessment_id": aid, "questions": qs,
               "unmatched_marking_material": out.unmatched_marking_material})


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def flags(paper: str, q: dict) -> list[str]:
    """Code checks: text and context each verbatim in the paper (line breaks and spacing ignored); marking material present."""
    out = []
    if squash(q["text"]) not in squash(paper):
        out.append("Question text not found in the paper")
    if q.get("context") and squash(q["context"]) not in squash(paper):
        out.append("Context not found in the paper")
    if not (q.get("marking_material") or "").strip():
        out.append("Has no marking material")
    return out


def confirmed_questions(conn: sqlite3.Connection, vid: str, aid: str) -> list[dict]:
    rows = conn.execute("SELECT question_id, context, text, options, type, marking_material FROM questions "
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
            "INSERT INTO questions (version_id, question_id, assessment_id, context, text, options, type, marking_material) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(vid, q.question_id, aid, q.context if (q.context or "").strip() else None, q.text, json.dumps(q.options) if q.options is not None else None, q.type,
              q.marking_material if (q.marking_material or "").strip() else None) for q in questions])
