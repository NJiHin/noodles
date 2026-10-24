"""Evaluation beside the app (spec 13): export inputs, merge traces into the frozen reference, score results."""
import json

import pytest

from noodles import eval as ev
from test_05_student import PAGES, PRE, answer, assess, course, drive, fake

QS = [{"question_id": "1", "text": "What does a loop do?", "options": None, "type": "short", "marking_material": "Repeats code."},
      {"question_id": "2", "text": "Why name variables?", "options": None, "type": "short", "marking_material": None},
      {"question_id": "3", "text": "Write a summing function.", "options": None, "type": "code", "marking_material": "Any loop."}]


@pytest.fixture
def dirs(client, tmp_path):
    return client.app_db.parent, tmp_path / "runs"


@pytest.fixture
def vid(client):
    v = course(client, "CS2030", PAGES)
    assess(client, v, cutoff=2, questions=QS)
    return v


def test_export_writes_each_keyed_question_with_the_passages_in_its_week_limit(client, dirs, vid):
    assert ev.export(dirs[0], vid) == ["quiz-q1"]  # no key and code questions get no entry
    got = json.loads((dirs[0] / "eval" / "CS2030" / vid / "inputs" / "quiz-q1.json").read_text())
    assert got["question"] == "What does a loop do?" and got["marking_material"] == "Repeats code."
    assert [p["passage_id"] for p in got["passages"]] == ["CS2030-w1-week1-p1", "CS2030-w2-week2-p1"]  # week 3 is past the cutoff
    assert got["passages"][1]["text"] == PAGES[2] and got["fingerprint"]


def test_export_with_a_prerequisite_includes_its_passages(client, dirs, vid):
    course(client, "CS1010", PRE)
    ev.export(dirs[0], vid, prerequisite="CS1010")
    got = json.loads((dirs[0] / "eval" / "CS2030" / vid / "inputs" / "quiz-q1.json").read_text())
    ids = [p["passage_id"] for p in got["passages"]]
    assert "CS1010-w3-week3-p1" in ids and "CS2030-w3-week3-p1" not in ids  # the prerequisite whatever its week


W1, W2 = "CS2030-w1-week1-p1", "CS2030-w2-week2-p1"
NIM = "not in materials"


def trace(dirs, vid, qid, n, steps, model="claude-test"):
    """A trace file as Claude Code writes it: each step's knowledge and its passages, or "not in materials"."""
    d = dirs[0] / "eval" / "CS2030" / vid / "traces"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{qid}.{n}.json").write_text(json.dumps({"model": model, "steps": [{"knowledge": k, "passages": p} for k, p in steps]}))


def traced(dirs, vid, qid, *runs):
    for n, steps in enumerate(runs, 1):
        trace(dirs, vid, qid, n, steps)


def test_merge_freezes_one_entry_per_traced_question(client, dirs, vid):
    ev.export(dirs[0], vid)
    traced(dirs, vid, "quiz-q1", [("Loops repeat a block.", [W2])], [("Loops repeat a block.", [W2, W1])],
           [("Loops repeat a block.", [W2]), ("Exit conditions.", NIM)])
    assert ev.merge(dirs[0], vid) == ["quiz-q1"]
    ref = json.loads((dirs[0] / "eval" / "CS2030" / vid / "reference.json").read_text())["quiz-q1"]
    assert ref["coverage"] == "gap"  # one trace found a step the materials don't teach
    assert ref["passages"] == [W2]  # W1 was cited by only one trace of three
    assert len(ref["traces"]) == 3 and ref["traces"][2]["steps"][1]["passages"] == NIM  # each trace kept, to explain a disagreement
    assert ref["fingerprint"] and ref["model"] == "claude-test" and ref["frozen_at"]
    trace(dirs, vid, "quiz-q1", 3, [("Loops repeat a block.", [W2])])  # a later trace never changes a frozen entry
    assert ev.merge(dirs[0], vid) == [] and ev.export(dirs[0], vid) == []


TWO = [{"question_id": "1", "text": "What does a loop do?", "options": None, "type": "short", "marking_material": "Repeats code."},
       {"question_id": "2", "text": "What is recursion?", "options": None, "type": "short", "marking_material": "A self call."}]


@pytest.fixture
def driven(client, dirs):
    """q1: the student cites W2, no gap, marked correct. q2: a "none" step (a gap), marked incorrect."""
    v = course(client, "CS2030", PAGES)
    assess(client, v, cutoff=2, questions=TWO)
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer(
        [("Recursion calls itself.", "none", [])] if "recursion" in m[1]["content"] else [("Loops repeat.", "course", [W2])], "A")
    fake(client).handlers["Mark"] = lambda m: {"verdict": "incorrect" if "recursion" in m[-1]["content"] else "correct", "reason": "."}
    assert drive(client, v)["status"] == "done"
    ev.export(dirs[0], v)
    return v


def test_score_against_the_reference(client, dirs, driven):
    traced(dirs, driven, "quiz-q1", *[[("Loops repeat a block.", [W1, W2])]] * 3)  # covered, both pages
    traced(dirs, driven, "quiz-q2", *[[("Recursion calls itself.", [W2])]] * 3)  # covered: the system's gap is a false one
    ev.merge(dirs[0], driven)
    s = ev.score(dirs[0], dirs[1], driven)
    rows = {r["question_id"]: r for r in s["rows"]}
    assert (rows["quiz-q1"]["reference"], rows["quiz-q1"]["system"], rows["quiz-q1"]["recall"]) == ("covered", "covered", 0.5)
    assert (rows["quiz-q2"]["reference"], rows["quiz-q2"]["system"], rows["quiz-q2"]["recall"]) == ("covered", "gap", 0.0)
    assert "Recursion calls itself." in rows["quiz-q2"]["detail"]  # the student's "none" step behind the false gap
    t = s["totals"]["all"]
    assert (t["questions"], t["agreement"], t["gaps_found"], t["gaps_missed"], t["false_gaps"]) == (2, 0.5, 0, 0, 1)
    assert (t["correct"], t["recall"]) == (0.5, 0.25)
    assert s["totals"]["quiz"] == t  # one assessment
    assert (dirs[0] / "eval" / "CS2030" / driven / "scores.csv").read_text().count("\n") == 3  # header and two rows


def test_score_uses_the_verdicts_after_overrides(client, dirs, driven):
    for q in ("quiz-q1", "quiz-q2"):
        traced(dirs, driven, q, *[[("Step.", [W2])]] * 3)
    ev.merge(dirs[0], driven)
    run = client.get(f"/versions/{driven}/review").json()["questions"][1]["run_id"]
    assert client.put(f"/runs/{run}/overrides/quiz-q2/student", json={"verdict": "correct"}).status_code == 200
    assert ev.score(dirs[0], dirs[1], driven)["totals"]["all"]["correct"] == 1.0  # q2 was marked incorrect, then overridden


def test_score_refuses_an_entry_whose_materials_changed(client, dirs, driven):
    for q in ("quiz-q1", "quiz-q2"):
        traced(dirs, driven, q, *[[("Step.", [W2])]] * 3)
    ev.merge(dirs[0], driven)
    assert client.put(f"/versions/{driven}/passages/{W1}", json={"text": "Corrected by hand."}).status_code == 200
    with pytest.raises(ValueError, match="quiz-q1"):
        ev.score(dirs[0], dirs[1], driven)


def test_question_without_a_result_is_listed_and_left_out_of_the_rates(client, dirs, vid):
    ev.export(dirs[0], vid)  # confirmed but never test-driven
    traced(dirs, vid, "quiz-q1", *[[("Loops are taught nowhere.", NIM)]] * 3)
    ev.merge(dirs[0], vid)
    s = ev.score(dirs[0], dirs[1], vid)
    assert s["rows"][0]["system"] == "no result"
    assert s["totals"]["all"]["questions"] == 0 and s["totals"]["all"]["recall"] == "n/a"  # no reference passages either


def test_score_with_labels_reports_detection_and_false_flags(client, dirs, driven):
    # results: q1 no gap and AI-exposed (both agents right); q2 a gap, nobody right
    labels = {"quiz-q1": {"gap": False, "exposure": "course_specific"},  # its exposure flag is a false one
              "quiz-q2": {"gap": True, "exposure": "ai_exposed"}}  # planted gap caught, planted exposure missed
    t = ev.score(dirs[0], dirs[1], driven, labels=labels)["totals"]
    assert t["coverage"] == {"planted": 1, "detected": 1, "detection_rate": 1.0, "false_flags": 0}
    assert t["exposure"] == {"planted": 1, "detected": 0, "detection_rate": 0.0, "false_flags": 1}
