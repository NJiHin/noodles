import json

from conftest import ingest, make_pdf, wait_run
from test_05_student import answer, assess, course, drive, fake

PAGES4 = {1: "Variables store values that a program can read and change later.",
          2: "Loops repeat a block of code until a stated condition becomes false.",
          3: "Functions group statements under a name.",
          4: "Recursion solves a problem by calling the same function on smaller input."}

QA = [{"question_id": "1", "text": "What does a loop do?", "options": None, "type": "short", "marking_material": "Repeats."}]
QB = [{"question_id": "1", "text": "What is recursion?", "options": None, "type": "short", "marking_material": "Self call."}]


def two_assessments(client, vid, qb=QB):
    assess(client, vid, cutoff=2, questions=QA)  # "Quiz" -> quiz-q1
    client.app.state.openai.handlers["QuestionSplit"] = lambda m: {"questions": qb, "unmatched_marking_material": []}
    r = client.post(f"/versions/{vid}/assessments", data={"name": "Final", "week_cutoff": 4, "current_format": "take_home"},
                    files=[("paper", ("final.pdf", make_pdf([qb[0]["text"]])))])
    assert wait_run(client, r.json()["run_id"])["status"] == "done"
    qs = next(a for a in client.get(f"/versions/{vid}/assessments").json() if a["assessment_id"] == "final")["questions"]
    assert client.put(f"/versions/{vid}/assessments/final/questions", json={"questions": [
        {k: q[k] for k in ("question_id", "text", "options", "type", "marking_material")} for q in qs]}).status_code == 200


def students(client):
    return [m[1]["content"] for s, _, m, _ in fake(client).calls if s == "StudentAnswer"]


def test_week4_edit_reruns_only_cutoff_4_students(client):
    v1 = course(client, "CS2030", PAGES4)
    two_assessments(client, v1)
    drive(client, v1)
    n = len(students(client))
    v2 = course(client, "CS2030", {**PAGES4, 4: "Recursion calls the function itself on a smaller input."})
    two_assessments(client, v2)
    drive(client, v2)
    assert set(students(client)[n:]) == {"What is recursion?"}


def orchestrator_inputs(client):
    return [json.loads(m[-1]["content"]) for s, _, m, _ in fake(client).calls if s == "MergedMap"]


def build(client, vid):
    run = client.post(f"/versions/{vid}/map-runs").json()["run_id"]
    assert wait_run(client, run)["status"] == "done"
    return client.get(f"/versions/{vid}/map").json()


def test_orchestrator_gets_previous_concepts_and_map_lists_id_diff(client):
    files = lambda p: ([(f"week{w}.pdf", make_pdf([t])) for w, t in p.items()], {f"week{w}.pdf": w for w in p})
    v1 = ingest(client, "CS2030", *files(PAGES4))
    m1 = build(client, v1)
    assert orchestrator_inputs(client)[0]["previous_concepts"] == []
    assert m1["id_diff"] is None  # first version
    renamed = [dict(c, concept_id="CS2030:renamed", name="renamed") if i == 0 else c for i, c in enumerate(m1["concepts"])]
    client.put(f"/versions/{v1}/map", json={"concepts": renamed})
    v2 = ingest(client, "CS2030", *files({**PAGES4, 4: "Recursion again, edited."}))
    m2 = build(client, v2)
    prev = orchestrator_inputs(client)[-1]["previous_concepts"]
    assert {"concept_id": "CS2030:renamed", "name": "renamed", "aliases": []} in prev
    assert m2["id_diff"]["previous_version"] == v1
    assert "CS2030:renamed" in m2["id_diff"]["disappeared"]
    assert m1["concepts"][0]["concept_id"] in m2["id_diff"]["new"]
    assert "CS2030:renamed" not in m2["id_diff"]["new"]


def changes(client, vid):
    return client.get(f"/versions/{vid}/changes").json()


def test_first_version_has_no_previous_run(client):
    v1 = course(client, "CS2030", PAGES4)
    two_assessments(client, v1)
    drive(client, v1)
    assert changes(client, v1)["previous"] is None


def test_changed_results_edited_question_and_depth(client):
    v1 = course(client, "CS2030", PAGES4)
    two_assessments(client, v1)
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer([("Loops repeat a block.", "course", ["CS2030-w2-week2-p1"])])
    drive(client, v1)
    v2 = course(client, "CS2030", {**PAGES4, 3: "Functions group statements under one name."})
    two_assessments(client, v2, qb=[dict(QB[0], text="What is recursion, briefly?")])
    m = client.get(f"/versions/{v2}/map").json()["concepts"]
    m[1]["occurrences"][0]["depth"] = "practised"  # CS2030:topic-w2, week 2: explained -> practised
    client.put(f"/versions/{v2}/map", json={"concepts": m})
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer([("Memoisation caches.", "none", [])])
    drive(client, v2)
    ch = changes(client, v2)
    assert ch["previous"]["version_id"] == v1
    q = {x["question_id"]: x for x in ch["questions"]}
    assert "quiz-q1" not in q  # cutoff 2: week 3 edit and a depth change don't touch its inputs, so it's cached
    gap = next(f for f in q["final-q1"]["fields"] if f["field"] == "gap")
    assert (gap["before"], gap["after"]) == (False, True)
    rec = next(f for f in q["final-q1"]["fields"] if f["field"] == "recommendation")
    assert (rec["before"], rec["after"]) == ("Change format", "Fix coverage first")
    assert q["final-q1"]["edited"] is True
    assert {"concept_id": "CS2030:topic-w2", "name": "CS2030 topic 2", "week": 2, "before": "explained",
            "after": "practised"} in ch["map"]["depth"]
    assert ch["counts"]["new_gaps"] == 1 and ch["counts"]["edited"] == 1 and ch["counts"]["depth"] == 1
