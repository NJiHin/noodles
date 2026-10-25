from test_05_student import PAGES, assess, course, drive, fake, review
from test_05_student import target  # noqa: F401  (fixture)


def step(claim, source="assumed_knowledge", reason="Entry requirement.", accepted_id=None):
    return {"claim": claim, "source": source, "evidence": [], "reason": reason, "accepted_id": accepted_id}


def decide(client, code, claim, decision):
    r = client.post(f"/courses/{code}/assumptions", json={"claim": claim, "decision": decision})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def steps_of(client, vid, qid="quiz-q1"):
    return review(client, vid)[qid]["answer"]["steps"]


def test_decisions_per_course_survive_versions(client, target):
    a = decide(client, "CS2030", "Integer division drops the remainder.", "accepted")
    r = decide(client, "CS2030", "Binary doubles when shifted left.", "rejected")
    assert decide(client, "CS2030", "Integer division drops the remainder.", "rejected") == a  # same claim: updated
    got = client.get("/courses/CS2030/assumptions").json()
    assert [(x["id"], x["decision"]) for x in got] == [(a, "rejected"), (r, "rejected")]
    assert client.get("/courses/CS1010/assumptions").json() == []
    assert client.post("/courses/CS2030/assumptions", json={"claim": "x", "decision": "maybe"}).status_code == 422
    v2 = course(client, "CS2030", {**PAGES, 1: "Variables hold values a program reads."})
    assess(client, v2)
    drive(client, v2)
    system = next(m for s, _, m, _ in fake(client).calls if s == "StudentAnswer")[0]["content"]
    assert f"#{a}" in system and "Integer division drops the remainder." in system


def test_prompt_lists_decided_claims_with_ids(client, target):
    a = decide(client, "CS2030", "Integer division drops the remainder.", "accepted")
    r = decide(client, "CS2030", "Binary doubles when shifted left.", "rejected")
    drive(client, target)
    system = next(m for s, _, m, _ in fake(client).calls if s == "StudentAnswer")[0]["content"]
    assert f"#{a}: Integer division drops the remainder." in system.split("Rejected")[0]
    assert f"#{r}: Binary doubles when shifted left." in system.split("Rejected")[1]


def test_accepted_step_not_reviewed_not_gap(client, target):
    a = decide(client, "CS2030", "Integer division drops the remainder.", "accepted")
    fake(client).handlers["StudentAnswer"] = lambda m, t: {"final_answer": "A", "steps": [
        step("Integer division drops the remainder.", reason=None, accepted_id=a), step("Shifting doubles.")]}
    drive(client, target)
    s = steps_of(client, target)
    assert s[0]["assumption"] == {"state": "accepted", "id": a}
    assert s[1]["assumption"] == {"state": "unreviewed"}
    assert review(client, target)["quiz-q1"]["gap"] is False
    assert client.get(f"/versions/{target}/summary").json()["figures"]["assumptions"] == 2  # one per question


def test_unknown_or_rejected_accepted_id_is_unreviewed(client, target):
    r = decide(client, "CS2030", "Binary doubles when shifted left.", "rejected")
    fake(client).handlers["StudentAnswer"] = lambda m, t: {"final_answer": "A", "steps": [
        step("Something else.", reason=None, accepted_id=999), step("Another thing.", reason=None, accepted_id=r)]}
    drive(client, target)
    assert [x["assumption"] for x in steps_of(client, target)] == [{"state": "unreviewed"}] * 2


def test_decision_after_run_shows_on_step_and_reruns_every_student(client, target):
    fake(client).handlers["StudentAnswer"] = lambda m, t: {"final_answer": "A", "steps": [step("Shifting doubles.")]}
    drive(client, target)
    n = fake(client).count("StudentAnswer")
    i = decide(client, "CS2030", "Shifting doubles.", "rejected")
    assert steps_of(client, target)[0]["assumption"] == {"state": "rejected", "id": i}
    q = review(client, target)["quiz-q1"]
    assert q["gap"] is True and q["recommendation"]["text"] == "Step 1 relies on knowledge you rejected."
    drive(client, target)
    assert fake(client).count("StudentAnswer") == n + 2  # both questions rerun
