import asyncio

from test_05_student import answer, assess, course, drive, fake, review, PAGES, PRE  # noqa: F401
from test_05_student import prereq, target  # noqa: F401  (fixtures)


def verdicts(client, vid, qid="quiz-q1"):
    return [(s["source"], s.get("grounding")) for s in review(client, vid)[qid]["answer"]["steps"]]


def test_code_check_unsupported_without_call(client, target, prereq):
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer([
        ("Made up.", "course", ["CS2030-w1-nope-p9"]),
        ("Recursion calls itself.", "course", ["CS2030-w3-week3-p1"]),  # after week N = 2
        ("Loops repeat.", "prerequisite", ["CS2030-w2-week2-p1"]),  # a target passage
        ("No citation.", "course", []),
        ("Loops repeat a block.", "course", ["CS2030-w2-week2-p1"]),
        ("Truth tables.", "prerequisite", ["CS1010-w3-week3-p1"]),
    ])
    assert drive(client, target, "CS1010")["status"] == "done"
    v = verdicts(client, target)
    assert [g["verdict"] for _, g in v] == ["unsupported"] * 4 + ["supported"] * 2
    checked = [m[-1]["content"] for s, _, m, _ in fake(client).calls if s == "Grounding"]
    assert len(checked) == 2  # only the two valid steps; the second question has the same steps (shared)
    assert all("Loops repeat a block." in c or "Truth tables." in c for c in checked)


def test_unsupported_is_gap_partial_is_not(client, target):
    # the checker can't see the question: the first check is unsupported, the other partial
    calls = []

    def grounding(m):
        calls.append(m)
        return {"verdict": "unsupported" if len(calls) == 1 else "partial", "reason": "Because."}
    fake(client).handlers["Grounding"] = grounding
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer(
        [("Loops repeat." if "loop do" in m[-1]["content"] else "Loops repeat code.", "course", ["CS2030-w2-week2-p1"])])
    assert drive(client, target)["status"] == "done"
    r = review(client, target)
    by_claim = {r[q]["answer"]["steps"][0]["grounding"]["verdict"]: r[q]["gap"] for q in ("quiz-q1", "quiz-q2")}
    assert by_claim == {"unsupported": True, "partial": False}



def test_checks_parallel_and_cached_per_step(client, target):
    live, peak = [0], [0]

    async def grounding(m):
        live[0] += 1
        peak[0] = max(peak[0], live[0])
        await asyncio.sleep(0.05)
        live[0] -= 1
        return {"verdict": "supported", "reason": "States it."}
    claims = ["Loops repeat a block.", "Variables store values."]
    fake(client).handlers["Grounding"] = grounding
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer([(c, "course", ["CS2030-w2-week2-p1"]) for c in claims])
    drive(client, target)
    assert peak[0] >= 2
    assert fake(client).count("Grounding") == 2  # both questions have the same two steps: one check each
    claims[1] = "Variables hold values."
    m = client.get(f"/versions/{target}/map").json()["concepts"]
    m[0]["aliases"] = ["new alias"]  # makes the student rerun; headings aren't part of the check
    client.put(f"/versions/{target}/map", json={"concepts": m})
    drive(client, target)
    assert fake(client).count("Grounding") == 3  # only the changed step is checked again
    assert "reason" in review(client, target)["quiz-q1"]["answer"]["steps"][0]["grounding"]
