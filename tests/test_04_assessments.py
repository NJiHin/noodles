import pytest

from conftest import ingest, make_pdf, wait_run

PAPER = ["Question 1a. What does a loop do in a program written in C?",
         "Question 1b. Which keyword exits a loop early? (A) break (B) stop",
         "Question 2. Write a function that returns the sum of a list."]
ANSWERS = ["1a. A loop repeats a block of code until its condition is false. 1b. A", "2. Any correct summing loop over the list earns full marks."]

SPLIT = {"questions": [
    {"question_id": "1a", "text": "What does a loop do in a program written in C?", "options": None, "type": "short",
     "marking_material": "A loop repeats a block of code until its condition is false."},
    {"question_id": "1b", "text": "Which keyword exits a loop early?", "options": ["break", "stop"], "type": "mcq",
     "marking_material": "A"},
    {"question_id": "2", "text": "Write a function that returns the sum of a list.", "options": None, "type": "code",
     "marking_material": "Any correct summing loop."},
], "unmatched_marking_material": []}


@pytest.fixture
def version(client):
    return ingest(client, "CS1010", [("week1.pdf", make_pdf(["Loops repeat a block of code until a condition is false."]))],
                  {"week1.pdf": 1})


def add(client, vid, name="Midterm", paper=PAPER, answers=ANSWERS, cutoff=6, fmt="invigilated_exam"):
    files = [("paper", ("paper.pdf", make_pdf(paper)))]
    if answers:
        files.append(("answers", ("answers.pdf", make_pdf(answers))))
    r = client.post(f"/versions/{vid}/assessments", data={"name": name, "week_cutoff": cutoff, "current_format": fmt},
                    files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert wait_run(client, body["run_id"])["status"] == "done"
    return body["assessment_id"]


def assessment(client, vid, aid):
    return next(a for a in client.get(f"/versions/{vid}/assessments").json() if a["assessment_id"] == aid)


@pytest.fixture
def split(client):
    client.app.state.openai.handlers["QuestionSplit"] = lambda m: SPLIT
    return SPLIT


def test_assessment_files_never_in_passages_or_fts(client, version, split):
    add(client, version)
    from noodles import db
    conn = db.connect(client.app_db)
    assert conn.execute("SELECT count(*) FROM passages WHERE text LIKE '%keyword exits%'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM passages_fts WHERE passages_fts MATCH '\"keyword\"'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM assessment_files WHERE text LIKE '%keyword exits%'").fetchone()[0] == 1


def test_question_not_in_paper_flagged(client, version, split):
    split["questions"][0]["text"] = "What does recursion do?"
    a = assessment(client, version, add(client, version))
    q = {x["question_id"]: x for x in a["questions"]}
    assert "not found in the paper" in " ".join(q["midterm-q1a"]["flags"])
    assert q["midterm-q1b"]["flags"] == []


def test_missing_marking_material_and_orphans_flagged(client, version, split):
    split["questions"][1]["marking_material"] = None
    split["unmatched_marking_material"] = ["3. An extra answer."]
    a = assessment(client, version, add(client, version))
    q = {x["question_id"]: x for x in a["questions"]}
    assert "no marking material" in " ".join(q["midterm-q1b"]["flags"])
    assert a["unmatched_marking_material"] == ["3. An extra answer."]


def test_sub_parts_are_separate_questions(client, version, split):
    a = assessment(client, version, add(client, version))
    assert [x["question_id"] for x in a["questions"]] == ["midterm-q1a", "midterm-q1b", "midterm-q2"]
    assert a["state"] == "draft"


def test_identical_reupload_makes_no_api_call(client, version, split):
    add(client, version)
    n = client.app.state.openai.count("QuestionSplit")
    add(client, version)
    assert client.app.state.openai.count("QuestionSplit") == n == 1


def test_split_sees_paper_and_answers(client, version, split):
    add(client, version)
    msg = client.app.state.openai.calls[-1][2][-1]["content"]
    assert "keyword exits" in msg and "summing loop" in msg


def test_confirm_with_no_marking_material_stores_null(client, version, split):
    aid = add(client, version, answers=None)
    qs = assessment(client, version, aid)["questions"]
    qs[0]["marking_material"] = None
    r = client.put(f"/versions/{version}/assessments/{aid}/questions", json={"questions": qs[:2]})
    assert r.status_code == 200, r.text
    a = assessment(client, version, aid)
    assert a["state"] == "confirmed" and len(a["questions"]) == 2
    from noodles import db
    row = db.connect(client.app_db).execute("SELECT marking_material FROM questions WHERE question_id = 'midterm-q1a'").fetchone()
    assert row[0] is None


def test_bad_cutoff_or_format_rejected(client, version):
    files = [("paper", ("paper.pdf", make_pdf(PAPER)))]
    for data in ({"name": "x", "week_cutoff": 0, "current_format": "take_home"},
                 {"name": "x", "week_cutoff": 3, "current_format": "oral"}):
        assert client.post(f"/versions/{version}/assessments", data=data, files=files).status_code == 422


def test_identical_reupload_keeps_confirmed_questions(client, version, split):
    aid = add(client, version)
    qs = assessment(client, version, aid)["questions"]
    qs[0]["text"] = "What does a loop do in a program written in C?"
    client.put(f"/versions/{version}/assessments/{aid}/questions", json={"questions": qs[:1]})
    add(client, version)
    assert len(assessment(client, version, aid)["questions"]) == 1
    add(client, version, paper=PAPER[:2])
    assert assessment(client, version, aid)["state"] == "draft"
