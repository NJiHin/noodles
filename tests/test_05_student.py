import json
import re
import sqlite3

import pytest

from conftest import ingest, make_pdf, wait_run
from noodles import db
from noodles.student import recheck_search, student_conn

PAGES = {1: "Variables store values that a program can read and change later.",
         2: "Loops repeat a block of code until a stated condition becomes false.",
         3: "Recursion solves a problem by calling the same function on smaller input."}
PRE = {1: "Binary numbers use only the digits zero and one.",
       3: "Truth tables list every combination of boolean inputs."}


def course(client, code, pages):
    """Ingest one PDF per week and confirm a map with one topic per week."""
    vid = ingest(client, code, [(f"week{w}.pdf", make_pdf([t])) for w, t in pages.items()],
                 {f"week{w}.pdf": w for w in pages})
    concepts = [{"concept_id": f"{code}:topic-w{w}", "name": f"{code} topic {w}", "aliases": [], "description": "",
                 "occurrences": [{"week": w, "depth": "explained", "evidence": [f"{code}-w{w}-week{w}-p1"]}]}
                for w in pages]
    assert client.put(f"/versions/{vid}/map", json={"concepts": concepts}).status_code == 200
    return vid


QUESTIONS = [
    {"question_id": "1", "text": "What does a loop do?", "options": None, "type": "short", "marking_material": "Repeats code."},
    {"question_id": "2", "text": "Which keyword exits a loop early?", "options": ["break", "stop"], "type": "mcq",
     "marking_material": "SECRET-ANSWER-A"},
    {"question_id": "3", "text": "Write a summing function.", "options": None, "type": "code", "marking_material": "Any loop."},
]


def assess(client, vid, cutoff=2, questions=QUESTIONS):
    client.app.state.openai.handlers["QuestionSplit"] = lambda m: {"questions": questions, "unmatched_marking_material": []}
    r = client.post(f"/versions/{vid}/assessments", data={"name": "Quiz", "week_cutoff": cutoff, "current_format": "online_quiz"},
                    files=[("paper", ("paper.pdf", make_pdf(["What does a loop do? OTHER-PAPER-TEXT"])))])
    assert wait_run(client, r.json()["run_id"])["status"] == "done"
    qs = next(a for a in client.get(f"/versions/{vid}/assessments").json())["questions"]
    r = client.put(f"/versions/{vid}/assessments/quiz/questions", json={"questions": [
        {k: q[k] for k in ("question_id", "text", "options", "type", "marking_material")} for q in qs]})
    assert r.status_code == 200, r.text


@pytest.fixture
def target(client):
    vid = course(client, "CS2030", PAGES)
    assess(client, vid)
    return vid


@pytest.fixture
def prereq(client):
    return course(client, "CS1010", PRE)


def fake(client):
    return client.app.state.openai


def drive(client, vid, prerequisite=None):
    r = client.post(f"/versions/{vid}/test-drives", json={"prerequisite": prerequisite})
    assert r.status_code == 200, r.text
    return wait_run(client, r.json()["run_id"])


def review(client, vid):
    return {q["question_id"]: q for q in client.get(f"/versions/{vid}/review").json()["questions"]}


def student_calls(client):
    return [(m, t) for s, _, m, t in fake(client).calls if s == "StudentAnswer"]


def answer(steps, final="B"):
    return {"final_answer": final, "steps": [{"claim": c, "source": s, "evidence": e, "reason": None, "accepted_id": None}
                                            for c, s, e in steps]}


def lookup(ids, n=1):
    return [{"type": "function_call", "call_id": f"c{i}", "name": "lookup_concept",
             "arguments": json.dumps({"topic_ids": ids})} for i in range(n)]


def outputs(messages):
    return [m["output"] for m in messages if m.get("type") == "function_call_output"]


def test_needs_reviewed_map_and_confirmed_questions(client):
    vid = ingest(client, "CS2030", [("week1.pdf", make_pdf([PAGES[1]]))], {"week1.pdf": 1})
    assert client.post(f"/versions/{vid}/test-drives", json={"prerequisite": None}).status_code == 409
    vid = course(client, "CS2031", PAGES)
    assert client.post(f"/versions/{vid}/test-drives", json={"prerequisite": None}).status_code == 409


def test_week_limit_on_topic_list_and_lookups(client, target, prereq):
    def student(messages, tools):
        if not outputs(messages):
            return lookup(tools[0]["parameters"]["properties"]["topic_ids"]["items"]["enum"])
        return answer([("Loops repeat code.", "course", ["CS2030-w2-week2-p1"])])
    fake(client).handlers["StudentAnswer"] = student
    run = drive(client, target, "CS1010")
    assert run["status"] == "done", run
    calls = student_calls(client)
    assert len(calls) == 2 * 2  # two non-code questions, one lookup round each
    for messages, tools in calls:
        system = messages[0]["content"]
        assert "CS2030:topic-w2" in system and "CS2030:topic-w3" not in system
        assert "CS1010:topic-w3" in system  # prerequisite not cut by week
        enum = tools[0]["parameters"]["properties"]["topic_ids"]["items"]["enum"] if tools else []
        assert "CS2030:topic-w3" not in enum
        for out in outputs(messages):
            assert "CS2030-w3" not in out and "Recursion" not in out
            assert "CS1010-w3-week3-p1" in out and "CS2030-w2-week2-p1" in out
    cfg = json.loads(next((client.app_db.parent.parent / "runs").glob(f"*/*/{run['run_id']}.jsonl")).read_text().splitlines()[0])
    assert cfg["target"] == target and cfg["prerequisite"] == prereq


def test_unlisted_topic_rejected_and_sixth_lookup_refused(client, target):
    seen = {}

    def student(messages, tools):
        if tools is None or len(outputs(messages)) >= 6:
            seen["outs"] = outputs(messages)
            return answer([("Loops repeat code.", "course", ["CS2030-w2-week2-p1"])])
        if not outputs(messages):
            seen["enum"] = tools[0]["parameters"]["properties"]["topic_ids"]["items"]["enum"]
            return lookup(["CS2030:nope"])
        return lookup(["CS2030:topic-w1"], 2 if len(outputs(messages)) == 4 else 1)  # 5th and 6th in one batch
    fake(client).handlers["StudentAnswer"] = student
    assert drive(client, target)["status"] == "done"
    assert seen["enum"] == ["CS2030:topic-w1", "CS2030:topic-w2"]
    outs = seen["outs"]
    assert "not a listed topic" in outs[0] and "CS2030-w1" not in outs[0]
    assert all("CS2030-w1-week1-p1" in o for o in outs[1:5])
    assert "limit" in outs[5] and "CS2030-w1-week1-p1" not in outs[5]
    assert sum(1 for _, t in student_calls(client) if t) == 2 * 5  # no tools offered once 5 lookups are used


def test_none_step_without_hits_keeps_label_no_extra_call(client, target):
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer([("Memoisation caches earlier results.", "none", []),
                                                                   ("Recursion calls itself.", "assumed_knowledge", [])])
    assert drive(client, target)["status"] == "done"  # "Recursion" is only in week 3: out of reach
    assert fake(client).count("Relabels") == 0
    steps = review(client, target)["quiz-q1"]["answer"]["steps"]
    assert [s["source"] for s in steps] == ["none", "assumed_knowledge"]
    assert [s["step_id"] for s in steps] == ["quiz-q1-s1", "quiz-q1-s2"]


def test_none_steps_with_hits_one_continued_call(client, target):
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer([("A loop repeats a block.", "none", []),
                                                                   ("Variables store values.", "none", []),
                                                                   ("Memoisation caches.", "none", [])])
    assert drive(client, target)["status"] == "done"
    assert fake(client).count("Relabels") == 2  # one per question, not per step
    messages = next(m for s, _, m, _ in fake(client).calls if s == "Relabels")
    assert messages[-2]["role"] == "assistant"  # continues the student's own conversation
    assert "CS2030-w2-week2-p1" in messages[-1]["content"] and "Memoisation" not in messages[-1]["content"]
    steps = review(client, target)["quiz-q1"]["answer"]["steps"]
    assert steps[0]["source"] == "course" and [p["passage_id"] for p in steps[0]["evidence"]] == ["CS2030-w2-week2-p1"]
    assert steps[1]["source"] == "course" and steps[1]["evidence"]
    assert steps[2]["source"] == "none"


def test_fts_syntax_in_claim(client, target):
    c = student_conn(client.app_db)
    for claim in ["n = 2k + 1", 'say "loop" AND (NOT x*) OR NEAR', "= + -", ""]:
        recheck_search(c, claim, target, 2, None)
    hits = recheck_search(c, "the loop's condition", target, 2, None)
    assert [h["passage_id"] for h in hits] == ["CS2030-w2-week2-p1"]


def test_none_step_shows_as_gap(client, target):
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer(
        [("Loops repeat.", "course", ["CS2030-w2-week2-p1"])] + ([("Memoisation caches.", "none", [])] if "loop do" in m[-1]["content"] else []))
    assert drive(client, target)["status"] == "done"
    r = review(client, target)
    assert r["quiz-q1"]["gap"] is True and r["quiz-q2"]["gap"] is False
    ev = r["quiz-q2"]["answer"]["steps"][0]["evidence"][0]
    assert ev == {"passage_id": "CS2030-w2-week2-p1", "course": "CS2030", "version_id": target, "week": 2,
                  "filename": "week2.pdf", "slug": "week2", "page": 1, "text": PAGES[2]}
    assert r["quiz-q3"]["answer"] is None and r["quiz-q3"]["type"] == "code"  # code questions skipped


def test_rerun_cached_and_map_edit_reruns(client, target):
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer([("A loop repeats a block.", "none", [])])
    drive(client, target)
    n = len(fake(client).calls)
    assert drive(client, target)["status"] == "done"
    assert len(fake(client).calls) == n
    m = client.get(f"/versions/{target}/map").json()["concepts"]
    m[0]["aliases"] = ["new alias"]
    assert client.put(f"/versions/{target}/map", json={"concepts": m}).status_code == 200
    before = fake(client).count("StudentAnswer")
    drive(client, target)
    assert fake(client).count("StudentAnswer") == before + 2


def test_student_never_reads_assessment_tables(client, target):
    c = student_conn(client.app_db)
    for t in ("assessments", "assessment_files", "questions"):
        with pytest.raises(sqlite3.DatabaseError):
            c.execute(f"SELECT * FROM {t}").fetchall()
    assert drive(client, target)["status"] == "done"
    for s, _, m, _ in fake(client).calls:
        if s in ("StudentAnswer", "Relabels"):
            text = json.dumps(m)
            assert "SECRET-ANSWER-A" not in text and "OTHER-PAPER-TEXT" not in text and "Repeats code." not in text
            assert len(re.findall(r"loop do\?|exits a loop early", text)) == 1  # only its own question


def test_citation_outside_week_limit_not_resolved(client, target):
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer([("Recursion calls itself.", "course", ["CS2030-w3-week3-p1"])])
    assert drive(client, target)["status"] == "done"
    assert review(client, target)["quiz-q1"]["answer"]["steps"][0]["evidence"] == [{"passage_id": "CS2030-w3-week3-p1"}]
