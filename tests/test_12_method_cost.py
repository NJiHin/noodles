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


def test_prices_not_set_gives_no_total(client, target, monkeypatch):
    monkeypatch.setattr(cost, "PRICES", {})
    drive(client, target)
    c = method(client, target)["cost"]
    assert c["total"] is None and c["by_type"]["student"]["input_tokens"] == 400
