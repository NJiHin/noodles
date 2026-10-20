from noodles.report import recommend
from test_05_student import PAGES, answer, assess, course, drive, fake, review

STEP = {"source": "course"}


def q(gap=False, student="correct", web="correct", steps=1, fmt="online_quiz", keyed=True, qtype="short"):
    marks = {"student": {"verdict": student}, "web": {"verdict": web}} if keyed else None
    return {"type": qtype, "current_format": fmt, "gap": gap, "marks": marks,
            "answer": {"steps": [STEP] * steps}}


def key(x):
    return recommend(x)["key"]


def test_rule_1_gap_first_whatever_exposure():
    for s, w in [("correct", "correct"), ("incorrect", "correct"), ("correct", "incorrect")]:
        assert key(q(gap=True, student=s, web=w)) == "fix_coverage"
    assert key(q(gap=True, keyed=False)) == "fix_coverage"


def test_rule_2_no_answer_key():
    r = recommend(q(keyed=False))
    assert r["key"] == "not_assessed" and "not assessed" in r["title"]


def test_rule_3_student_wrong():
    assert key(q(student="incorrect", web="correct")) == "review_untaught"
    assert key(q(student="partial", web="partial")) == "review_broken"


def test_rule_4_student_right_web_wrong():
    r = recommend(q(web="incorrect", fmt="invigilated_exam"))
    assert r["key"] == "keep_open" and r["group"] == "Could be open or take-home"
    assert recommend(q(web="incorrect", fmt="take_home"))["group"] == "Keep as is"


def test_rule_5_lookup_and_reasoning_add_a_check():
    lookup, reasoning = recommend(q(steps=1)), recommend(q(steps=2))
    assert lookup["key"] == "closed_book" and reasoning["key"] == "open_book_or_redesign"
    assert recommend(q(steps=0))["key"] == "closed_book"
    for r in (lookup, reasoning):
        assert "add a check: oral defence, staged submissions or an in-class component" in r["text"]
        assert r["group"] == "Change format"
    assert lookup["facts"].startswith("AI-exposed") and "Lookup: 1 knowledge step" in lookup["facts"]


def test_matching_current_format_reads_keep_as_is():
    r = recommend(q(steps=1, fmt="invigilated_exam"))
    assert r["key"] == "closed_book" and r["title"] == "Keep as is" and r["group"] == "Keep as is"


def test_code_question_not_assessed():
    r = recommend({**q(), "type": "code", "answer": None, "marks": None})
    assert r["key"] == "code" and r["title"] == "Not assessed (code question)"


def test_summary_counts_match_questions(client):
    vid = course(client, "CS2030", PAGES)
    assess(client, vid, questions=[
        {"question_id": "1", "text": "What does a loop do?", "options": None, "type": "short", "marking_material": "Repeats."},
        {"question_id": "2", "text": "Which keyword exits a loop early?", "options": ["break", "stop"], "type": "mcq", "marking_material": "B"},
        {"question_id": "3", "text": "Why name variables?", "options": None, "type": "short", "marking_material": None},
        {"question_id": "4", "text": "Write a summing function.", "options": None, "type": "code", "marking_material": "Loop."},
    ])
    fake(client).handlers["StudentAnswer"] = lambda m, t: answer(
        [("Loops repeat a block.", "course", ["CS2030-w2-week2-p1"])] + ([("Memo.", "none", [])] if "Why name" in m[-1]["content"] else []), "A")
    assert drive(client, vid)["status"] == "done"
    r = review(client, vid)
    recs = {k: x["recommendation"]["key"] for k, x in r.items()}
    assert recs == {"quiz-q1": "closed_book", "quiz-q2": "review_broken", "quiz-q3": "fix_coverage", "quiz-q4": "code"}
    s = client.get(f"/versions/{vid}/summary").json()
    assert s["assessed"] == 3 and s["keep"] == 0
    assert s["figures"] == {"gaps": 1, "ai_exposed": 1}
    assert [(a["key"], a["questions"]) for a in s["actions"]] == [
        ("fix_coverage", ["quiz-q3"]), ("review", ["quiz-q2"]), ("change_format", ["quiz-q1"])]
    assert s["matrix"] == {"ai_exposed": ["quiz-q1"], "course_specific": [], "neither_taught": [], "broken_or_gap": ["quiz-q2"]}
    assert s["assessments"] == [{"assessment_id": "quiz", "week_cutoff": 2, "current_format": "online_quiz",
                                 "segments": ["ai", "other", "gap"], "groups": {"Change format": 1, "Review the question": 1,
                                                                                "Fix coverage first": 1}}]
