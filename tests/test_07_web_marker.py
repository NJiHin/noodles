import json

import pytest

from conftest import ingest, make_pdf
from test_05_student import PAGES, answer, assess, course, drive, fake, review

QS = [
    {"question_id": "1", "text": "What does a loop do?", "options": None, "type": "short", "marking_material": "Repeats a block of code."},
    {"question_id": "2", "text": "Which keyword exits a loop early?", "options": ["break", "stop"], "type": "mcq", "marking_material": "A"},
    {"question_id": "3", "text": "Why name variables?", "options": None, "type": "short", "marking_material": None},
]


@pytest.fixture
def target(client):
    vid = course(client, "CS2030", PAGES)
    assess(client, vid, questions=QS)
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer([("Loops repeat a block.", "course", ["CS2030-w2-week2-p1"])], "A")
    return vid


def test_mcq_exact_match_no_call(client, target):
    fake(client).handlers["WebAnswer"] = lambda m: {"final_answer": "stop", "sources": ["https://example.org/a"]}
    assert drive(client, target)["status"] == "done"
    q = review(client, target)["quiz-q2"]
    assert q["marks"]["student"]["verdict"] == "correct" and q["marks"]["web"]["verdict"] == "incorrect"
    assert q["web"] == {"final_answer": "stop", "sources": ["https://example.org/a"]}
    marked = [m[-1]["content"] for s, _, m, _ in fake(client).calls if s == "Mark"]
    assert not any("exits a loop early" in c for c in marked)


def test_marker_input_blind_to_steps_and_agent(client, target):
    assert drive(client, target)["status"] == "done"
    marked = [json.dumps(m) for s, _, m, _ in fake(client).calls if s == "Mark"]
    assert len(marked) == 1  # q1: student and web both answered "A": one shared call; q2 by code; q3 has no key
    for text in marked:
        assert "Loops repeat a block." not in text and "CS2030-w2" not in text
        assert "student" not in text.lower() and "web" not in text.lower()
        assert "Repeats a block of code." in text and "What does a loop do?" in text


def test_partial_counts_as_wrong(client, target):
    fake(client).handlers["Mark"] = lambda m: {"verdict": "partial", "reason": "Half of it."}
    drive(client, target)
    q = review(client, target)["quiz-q1"]
    assert q["marks"]["student"]["verdict"] == "partial" and q["marks"]["web"]["verdict"] == "partial"
    assert q["exposure"] == "broken_or_gap"


def test_no_marking_material_not_assessed(client, target):
    drive(client, target)
    q = review(client, target)["quiz-q3"]
    assert q["exposure"] == "not_assessed" and q["marks"] is None
    assert review(client, target)["quiz-q1"]["exposure"] == "ai_exposed"


def test_material_edit_reuses_web_answer(client, target):
    drive(client, target)
    n = fake(client).count("WebAnswer")
    v2 = course(client, "CS2030", {**PAGES, 2: "While loops check their condition before each pass."})
    assess(client, v2, questions=QS)
    assert drive(client, v2)["status"] == "done"
    assert fake(client).count("WebAnswer") == n
    assert fake(client).count("StudentAnswer") > 3


def test_override_changes_exposure_and_persists(client, target):
    run = drive(client, target)["run_id"]
    assert review(client, target)["quiz-q1"]["exposure"] == "ai_exposed"
    r = client.put(f"/runs/{run}/overrides/quiz-q1/web", json={"verdict": "incorrect"})
    assert r.status_code == 200, r.text
    q = review(client, target)["quiz-q1"]
    assert q["exposure"] == "course_specific"
    assert q["marks"]["web"]["verdict"] == "incorrect" and q["marks"]["web"]["overridden"] == "correct"
    assert client.put(f"/runs/{run}/overrides/quiz-q1/web", json={"verdict": "wrong"}).status_code == 422
    assert client.put(f"/runs/{run}/overrides/quiz-q9/web", json={"verdict": "correct"}).status_code == 404


def test_true_false_marked_near_exact_and_unclear_flagged(client):
    vid = course(client, "CS2030", PAGES)
    tf = [{"question_id": "1", "text": "Loops repeat a block of code.", "options": None, "type": "true_false", "marking_material": "T"},
          {"question_id": "2", "text": "Which keyword exits a loop early?", "options": ["break", "stop"], "type": "mcq", "marking_material": "A"}]
    assess(client, vid, questions=tf)
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer([], "True. Loops repeat a block.")
    fake(client).handlers["WebAnswer"] = lambda m: {"final_answer": "**True.** ([example.org](https://example.org/a))", "sources": []}
    assert drive(client, vid)["status"] == "done"
    q = review(client, vid)["quiz-q1"]
    assert q["marks"]["web"]["verdict"] == "correct" and not q["marks"]["web"].get("unclear")
    s = q["marks"]["student"]
    assert s["verdict"] == "incorrect" and s["unclear"] is True and "True or False" in s["reason"]
    s = review(client, vid)["quiz-q2"]["marks"]["student"]  # MCQ: "True. Loops…" is no option either
    assert s["unclear"] is True and "option" in s["reason"]

