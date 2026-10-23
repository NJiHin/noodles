import pytest

from noodles import cost
from test_05_student import PAGES, assess, course, drive, fake
from test_05_student import target  # noqa: F401  (fixture)

PRICES = {"gpt-6-luna": {"input": 1.0, "cached_input": 0.1, "output": 4.0},
          "gpt-6-sol": {"input": 5.0, "cached_input": 0.5, "output": 20.0}}


@pytest.fixture(autouse=True)
def prices(monkeypatch):
    monkeypatch.setattr(cost, "PRICES", PRICES)
    monkeypatch.setattr(cost, "WEB_SEARCH", 0.01)


def method(client, vid):
    return client.get(f"/versions/{vid}/method").json()


def test_cost_sums_new_records_and_cached_rerun_is_free(client, target):
    drive(client, target)
    m = method(client, target)
    # fake usage per request: 100 input (0 cached), 20 output. Two questions; per question: 2 student requests
    # (lookup, answer), 1 web (sol + 1 search); marker: q1 by LLM (shared by both answers), q2 by code.
    luna = (2 * 2 + 1 + 1) * (100 * 1.0 + 20 * 4.0) / 1e6  # one grounding: both cite the same step
    sol = 2 * (100 * 5.0 + 20 * 20.0) / 1e6
    assert m["cost"]["total"] == pytest.approx(luna + sol + 2 * 0.01)
    assert m["cost"]["web_search_calls"] == 2
    assert m["cost"]["by_type"]["web"]["web_search_cost"] == pytest.approx(0.02)
    drive(client, target)
    m = method(client, target)
    assert m["cost"]["total"] == 0 and m["cost"]["web_search_calls"] == 0
    assert m["run"]["rerun"] == 0 and m["run"]["questions"] == 3


def test_rerun_counts_questions_with_a_new_call(client, target):
    drive(client, target)
    v2 = course(client, "CS2030", {**PAGES, 2: "Loops run a block of code again while a condition holds."})
    assess(client, v2)
    drive(client, v2)
    m = method(client, v2)
    assert m["run"]["rerun"] == 2  # both questions have cutoff 2, and week 2 changed
    assert m["run"]["passages"] == 3 and m["run"]["topics"] == 3 and m["run"]["assessments"] == 1
    assert m["run"]["models"] == ["gpt-6-luna", "gpt-6-sol"]
    assert m["run"]["compared_with"]["version_id"] == target


def test_method_lists_every_run_of_the_course_with_its_cost(client, target):
    first = drive(client, target)["run_id"]
    v2 = course(client, "CS2030", {**PAGES, 2: "Loops run a block of code again while a condition holds."})
    assess(client, v2)
    second = drive(client, v2)["run_id"]
    m = method(client, v2)
    runs = m["runs"]
    assert [r["kind"] for r in runs] == ["split", "test_drive", "split", "test_drive"]  # every version, oldest first
    assert runs[1]["run_id"] == first and runs[3]["run_id"] == second and runs[1]["questions"] == 2  # the code question is not run
    assert runs[0]["assessment_id"] == "quiz" and runs[1]["new_calls"] > 0
    assert m["runs_total"] == pytest.approx(sum(r["cost"] for r in runs))
    assert runs[3]["cost"] == pytest.approx(m["cost"]["total"])


def test_prices_not_set_gives_no_totals(client, target, monkeypatch):
    monkeypatch.setattr(cost, "PRICES", {})
    drive(client, target)
    m = method(client, target)
    assert m["cost"]["total"] is None and m["cost"]["by_type"]["student"]["input_tokens"] == 400
    assert m["runs_total"] is None and all(r["cost"] is None for r in m["runs"] if r["new_calls"])
