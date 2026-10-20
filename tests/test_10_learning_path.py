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
    lp = client.get(f"/versions/{vid}/learning-path").json()
    return lp, {t["concept_id"]: t for t in lp["topics"]}


def test_passage_with_two_topics_counts_for_both(client):
    _, t = setup(client)
    assert t["CS2030:variables"]["questions"] == ["quiz-q1", "quiz-q2"]
    assert t["CS2030:call-stack"]["questions"] == ["quiz-q1", "quiz-q2"]


def test_assumed_or_none_step_topic_not_assessed(client):
    lp, t = setup(client)
    assert t["CS2030:loops"]["questions"] == [] and t["CS2030:loops"]["finding"] == "not_assessed"


def test_only_mentioned_up_to_cutoff(client):
    _, t = setup(client)
    cs = t["CS2030:call-stack"]
    assert cs["finding"] == "only_mentioned"
    m = cs["mentioned"][0]
    assert m["question_id"] == "quiz-q1" and m["week"] == 1 and m["page"] == 1 and m["slug"] == "week1"
    assert t["CS2030:variables"]["finding"] is None
    assert cs["depths"] == {"1": "mentioned", "3": "worked_example"}


def test_never_cited_topic_not_assessed(client):
    lp, t = setup(client)
    assert t["CS2030:recursion"]["finding"] == "not_assessed"
    assert lp["weeks"] == [1, 2, 3] and lp["assessments"] == [{"assessment_id": "quiz", "week_cutoff": 2}]
