"""Stage 2: the student agent (topic list, lookup_concept and calculate tool loop) and the re-check of uncited steps.

Student-facing queries go through student_conn(), which can't read the assessment tables.
"""
import ast
import asyncio
import json
import math
import operator
import re
import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from noodles import db
from noodles.coursemap import topic_label
from noodles.grounding import ground
from noodles.web import mark, question_text, web_agent
from noodles.llm import LUNA, Run, add_usage

STUDENT_V, RECHECK_V = "student-v14", "recheck-v1"  # v14: "none" also covers information neither given nor taught
MAX_LOOKUPS, RECHECK_HITS, MAX_CALCS = 5, 3, 30
Source = Literal["course", "prerequisite", "assumed_knowledge", "general_knowledge", "none"]
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

Answer the exam question concisely, as in an exam. List the steps of your answer: the knowledge each one brings in, with pure reasoning folded into those steps' claims. Every answer has at least one step, so a reader can see what it rests on. As a university student you already know secondary-school and pre-university (A-level/JC) mathematics and general knowledge, such as arithmetic, basic algebra, reading a table and substituting values into a formula you are given; anything printed in the question itself (its data, tables, and any formula it gives you) needs no source either. When your answer rests only on these, say so in one "general_knowledge" step, e.g. "S_x is the sum of the x column, as the question defines it." Never use "general_knowledge" for subject knowledge of this course. Exception: when the question says something was taught in class (e.g. "the normal equations discussed in class") and your answer uses it, knowing it is a step even if the question prints it: look for it in the course passages like any other step. A part of the question that doesn't use it (e.g. one that only asks for a sum from the table) gets no such step. Write any mathematics in LaTeX inside \\( \\) (inline) or \\[ \\] (display). For each step give its source:
- "course": you found it in a passage of {course} weeks 1 to {n}. Cite the passage IDs as evidence.
- "prerequisite": you found it in a passage of the prerequisite course. Cite the passage IDs as evidence.
- "assumed_knowledge": something beyond pre-university level that the course's stated entry requirements imply (e.g. its prerequisite course) but that isn't in the provided materials. Give a one-line reason. Example: "A square matrix is invertible exactly when its determinant is non-zero." with reason "Linear algebra is a stated prerequisite of the course."
- "general_knowledge": school-level knowledge or something printed in the question, as above. Leave evidence empty.
- "none": subject knowledge or information the answer needs that you wouldn't already know and can't find in the question or the course or prerequisite materials. Examples: "Memoisation caches results." when no passage covers memoisation; "The mean of Sales in the Carseats data is needed." when neither the question nor the materials give it.
Use "prerequisite" whenever the material exists there; use "assumed_knowledge" only when it doesn't. When unsure between "assumed_knowledge" and "none", choose "none".
Cite only passage IDs you were shown. Leave evidence empty for "assumed_knowledge", "general_knowledge" and "none", and reason and accepted_id null unless stated below.
final_answer is the answer alone, with no explanation: your reasoning belongs in the steps. If you can't attempt the question, set final_answer to null and still list the steps you managed.

{decided}Everything you state, in your steps and your final answer, must come from one of three places:
- the question itself (its data, tables and given formulas);
- a tool result: a calculate result for any number you work out, or a passage from lookup_concept for course content;
- general knowledge, labelled as a general_knowledge step.
If a tool can give you something, call the tool instead of writing it from memory, even inside a step's claim. You answer each part of a question on its own and can't see the other parts' answers, so work out anything you need from them again.

Your tools:
- lookup_concept(topic_ids): returns every course passage tagged with those topics, with its ID. Use it for any subject knowledge of this course; you don't need it for general knowledge or what the question gives. At most {max} calls.
- calculate(expression, label): evaluates arithmetic exactly. Use it for every number you work out. At most {max_calc} calls.

The topics you have been taught:
{topics}"""

RECHECK = """A keyword search of the materials you can see found passages for some of your uncited steps (numbered from 1 in your answer). For each step below, return its corrected label: "course" or "prerequisite" with the passage IDs that support it, or keep it "none" or "assumed_knowledge" (with its reason) if these passages don't cover it.

"""


CALC = {"type": "function", "name": "calculate", "strict": True,
        "description": "Evaluates an arithmetic expression: numbers, + - * / % ** (or ^) and brackets, and the functions sqrt, log, "
                       "exp, abs and round. Returns the result, or an error. label: what the result is, e.g. \"S_xy\".",
        "parameters": {"type": "object", "additionalProperties": False, "required": ["expression", "label"],
                       "properties": {"expression": {"type": "string"}, "label": {"type": "string"}}}}
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
FUNCS = {"sqrt": math.sqrt, "log": math.log, "exp": math.exp, "abs": abs, "round": round}


def calculate(expression: str) -> str:
    """The student's calculator: arithmetic only, by walking the parsed expression (never eval)."""
    def ev(n):
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and (abs(b) > 1000 or abs(a) > 1e100):
                raise ValueError("power too large")
            return OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords:
            return FUNCS[n.func.id](*map(ev, n.args))
        raise ValueError("only numbers, + - * / % ** and sqrt, log, exp, abs, round are allowed")
    try:
        if len(expression) > 500:
            raise ValueError("expression too long")
        # "^" means a power, as on a calculator; rewriting it keeps power's precedence (Python's ^ binds below + and *)
        x = ev(ast.parse(expression.replace("^", "**"), mode="eval").body)
        return str(x) if isinstance(x, int) else format(x, ".12g")
    except SyntaxError:
        return ("Error: not an expression the calculator can read. Use numbers only, no placeholders or names: "
                "work out any value you still need first (e.g. a sum from the table), then put the number in.")
    except (ValueError, TypeError, ZeroDivisionError, OverflowError, RecursionError) as e:
        return f"Error: {e}"


def tool(ids: list[str]) -> dict:
    return {"type": "function", "name": "lookup_concept", "strict": True,
            "description": "Every passage tagged with these topics, with its ID and heading.",
            "parameters": {"type": "object", "additionalProperties": False, "required": ["topic_ids"],
                           "properties": {"topic_ids": {"type": "array", "items": {"type": "string", "enum": ids}}}}}


def decisions_of(conn: sqlite3.Connection, course: str) -> list[dict]:
    """The professor's assumed-knowledge decisions for a course (carried across versions)."""
    return [dict(r) for r in conn.execute("SELECT id, claim, decision FROM assumed_knowledge WHERE course_code = ? "
                                          "ORDER BY id", (course,))]


def decided_text(decisions: list[dict]) -> str:
    """The decided claims section of the student prompt (empty if there are none)."""
    acc = [f"#{d['id']}: {d['claim']}" for d in decisions if d["decision"] == "accepted"]
    rej = [f"#{d['id']}: {d['claim']}" for d in decisions if d["decision"] == "rejected"]
    out = ""
    if acc:
        out += ("Accepted claims: you may rely on these. A step that does is \"assumed_knowledge\" with accepted_id set "
                "to the claim's number and reason null.\n" + "\n".join(acc) + "\n\n")
    if rej:
        out += ("Rejected claims: students are not assumed to know these. A step that needs one is \"none\".\n"
                + "\n".join(rej) + "\n\n")
    return out


async def student(run: Run, conn: sqlite3.Connection, q: dict, course: str, target: str, prereq: str | None,
                  prereq_course: str | None, decisions: list[dict]) -> dict:
    """Run the student on one question, then the re-check. Returns the student output for the question."""
    n = q["week_cutoff"]
    listed = topics(conn, target, n, prereq)
    ids = [t["concept_id"] for t in listed]
    system = PROMPT.format(prereq=prereq_course or "no prerequisite courses", n=n, course=course, max=MAX_LOOKUPS, max_calc=MAX_CALCS,
                           decided=decided_text(decisions),
                           topics="\n".join(f"{t['concept_id']} | {topic_label(t['name'], json.loads(t['aliases']))} | "
                                            f"{t['description'] or ''}" for t in listed) or "(none)")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question_text(q)}]

    async def loop():
        convo, usage, lookups, calcs = list(messages), {}, 0, 0
        worked: list[str] = []  # each distinct successful calculation, shown to the professor as a step
        failed: set[str] = set()
        while True:
            tools = ([tool(ids)] if ids and lookups < MAX_LOOKUPS else []) + ([CALC] if calcs < MAX_CALCS else [])
            out, u = await run.request("student", LUNA, convo, StudentAnswer, tools or None)
            usage = add_usage(usage, u)
            if not isinstance(out, list):
                return out.model_dump(), usage, {"conversation": convo + [{"role": "assistant", "content": out.model_dump_json()}],
                                                 "lookups": lookups, "calculations": worked}
            for call in out:
                convo.append(call)
                if call["name"] == "calculate":
                    calcs += 1
                    try:
                        args = json.loads(call["arguments"])
                        result = ("Error: this expression already failed. Don't send it again: work out the values it needs "
                                  "first, then send the numbers.") if args["expression"] in failed else calculate(args["expression"])
                        if result.startswith("Error"):
                            failed.add(args["expression"])
                        line = f"{args.get('label') or 'Calculation'}: {args['expression']} = {result}"
                        if not result.startswith("Error") and line not in worked:
                            worked.append(line)
                    except (ValueError, KeyError, TypeError):
                        result = "Rejected: arguments must be {\"expression\": \"...\", \"label\": \"...\"}."
                else:
                    lookups += 1
                    result = tool_output(conn, call, ids, lookups, target, n, prereq)
                convo.append({"type": "function_call_output", "call_id": call["call_id"], "output": result})

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
    # the calculator's working, after the knowledge steps: never grounded, never a gap, not a knowledge step
    steps += [{"claim": c, "source": "calculation", "evidence": [], "reason": None, "accepted_id": None} for c in rec["calculations"]]
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
    """Every question in parallel: student (re-check, grounding) alongside the web agent, then the marker.
    Each question's result is written to the run log."""
    conn = student_conn(db_path)
    try:
        decisions = decisions_of(conn, course)

        async def one(q):
            async def course_side():
                a = await student(run, conn, q, course, target, prereq, prereq_course, decisions)
                return a, await ground(run, conn, a, target, prereq)
            (answer, checks), web = await asyncio.gather(course_side(), web_agent(run, q))
            marks = None
            if q["marking_material"]:
                s, w = await asyncio.gather(mark(run, q, answer["final_answer"]), mark(run, q, web["final_answer"]))
                marks = {"student": s, "web": w}
            run.write({"type": "answer", **answer, "grounding": checks, "web": web, "marks": marks})
        await asyncio.gather(*(one(q) for q in questions))
    finally:
        conn.close()
