from conftest import ingest, make_pdf
from test_05_student import PAGES, assess, drive, fake


def occ(week, depth, *pages):
    return {"week": week, "depth": depth, "evidence": [f"CS2030-w{p}-week{p}-p1" for p in pages]}


def topic(name, *occurrences):
    return {"concept_id": f"CS2030:{name}", "name": name, "aliases": [], "description": "", "occurrences": list(occurrences)}


def setup(client):
    vid = ingest(client, "CS2030", [(f"week{w}.pdf", make_pdf([t])) for w, t in PAGES.items()], {f"week{w}.pdf": w for w in PAGES})
    concepts = [
        topic("variables", occ(1, "explained", 1)),
        topic("call-stack", occ(1, "mentioned", 1), occ(3, "worked_example", 3)),  # deeper only after the cutoff
        topic("loops", occ(2, "practised", 2)),
        topic("recursion", occ(3, "explained", 3)),
    ]
    assert client.put(f"/versions/{vid}/map", json={"concepts": concepts}).status_code == 200
    assess(client, vid, cutoff=2)
    fake(client).handlers["StudentAnswer"] = lambda m, t: {"final_answer": "A", "steps": [
        {"claim": "Variables hold values.", "source": "course", "evidence": ["CS2030-w1-week1-p1"], "reason": None, "accepted_id": None},
        {"claim": "Iteration recurs.", "source": "assumed_knowledge", "evidence": [], "reason": "Known.", "accepted_id": None},
    ]}
    assert drive(client, vid)["status"] == "done"
    s = client.get(f"/versions/{vid}/summary").json()
    review = {q["question_id"]: q for q in client.get(f"/versions/{vid}/review").json()["questions"]}
    return s, {t["concept_id"]: t for t in s["coverage"]["topics"]}, review


def test_passage_with_two_topics_counts_for_both(client):
    _, t, _ = setup(client)
    assert t["CS2030:variables"]["assessed"] and t["CS2030:call-stack"]["assessed"]


def test_assumed_or_none_step_topic_not_assessed(client):
    _, t, _ = setup(client)
    assert not t["CS2030:loops"]["assessed"]


def test_only_mentioned_up_to_cutoff_flagged_on_the_question(client):
    _, _, review = setup(client)
    [m] = review["quiz-q1"]["only_mentioned"]
    assert m["name"] == "call-stack" and m["week"] == 1 and m["page"] == 1 and m["slug"] == "week1" and m["week_cutoff"] == 2


def test_summary_coverage_by_week_and_never_assessed_count(client):
    s, t, _ = setup(client)
    assert not t["CS2030:recursion"]["assessed"] and t["CS2030:recursion"]["first_week"] == 3
    assert s["coverage"]["weeks"] == [1, 2, 3] and s["coverage"]["assessments"] == [{"assessment_id": "quiz", "week_cutoff": 2}]
    assert s["figures"]["never_assessed"] == 2  # loops, recursion


def test_review_lists_the_topics_each_question_tests_by_week(client):
    _, _, review = setup(client)
    # step 1 cites the week 1 passage, tagged with variables and call-stack; the assumed step adds nothing
    assert review["quiz-q1"]["topics"] == [{"week": 1, "concept_id": "CS2030:call-stack", "name": "call-stack"},
                                           {"week": 1, "concept_id": "CS2030:variables", "name": "variables"}]
