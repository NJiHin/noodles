import asyncio
import json
import re

import pytest

from conftest import ingest, make_pdf, wait_run

W = {
    1: ["Variables store values that a program can read and change later.",
        "Expressions combine values with operators to compute new values."],
    2: ["Loops repeat a block of code until a stated condition becomes false."],
    3: ["Recursion solves a problem by calling the same function on smaller input."],
}


def files(weeks=W):
    return [(f"week{w}.pdf", make_pdf(pages)) for w, pages in weeks.items()], {f"week{w}.pdf": w for w in weeks}


@pytest.fixture
def version(client):
    return ingest(client, "CS1010", *files())


def run_map(client, vid):
    run = client.post(f"/versions/{vid}/map-runs").json()["run_id"]
    return wait_run(client, run)


def fake(client):
    return client.app.state.openai


def log(client, run):
    path = next((client.app_runs).glob(f"*/*/{run}.jsonl"))
    return [json.loads(x) for x in path.read_text().splitlines()]


@pytest.fixture(autouse=True)
def runs_dir(client, tmp_path):
    client.app_runs = tmp_path / "runs"


def test_each_extractor_sees_only_its_week(client, version):
    assert run_map(client, version)["status"] == "done"
    calls = [m for s, _, m, _ in fake(client).calls if s == "WeekRecords"]
    assert len(calls) == 3
    for msgs in calls:
        user = msgs[-1]["content"]
        week = int(re.match(r"Week (\d+)", user).group(1))
        ids = re.findall(r"^\[(\S+)\]", user, re.M)
        assert ids and all(f"-w{week}-" in i for i in ids)


def test_identical_rerun_makes_no_calls_and_same_map(client, version):
    run_map(client, version)
    first = client.get(f"/versions/{version}/map").json()["concepts"]
    n = len(fake(client).calls)
    assert run_map(client, version)["status"] == "done"
    assert len(fake(client).calls) == n
    assert client.get(f"/versions/{version}/map").json()["concepts"] == first


def test_changing_one_week_reruns_only_that_extractor(client, version):
    run_map(client, version)
    before = fake(client).count("WeekRecords"), fake(client).count("MergedMap")
    v2 = ingest(client, "CS1010", *files({**W, 2: ["While loops check their condition before each pass."]}))
    assert run_map(client, v2)["status"] == "done"
    assert fake(client).count("WeekRecords") == before[0] + 1
    assert fake(client).count("MergedMap") == before[1] + 1


def test_interrupted_run_resumes_without_repeating_calls(client, version):
    f = fake(client)
    ok = f.handlers["MergedMap"]
    f.handlers["MergedMap"] = lambda m: (_ for _ in ()).throw(ConnectionError("network down"))
    assert run_map(client, version)["status"] == "failed"
    f.handlers["MergedMap"] = ok
    assert run_map(client, version)["status"] == "done"
    assert f.count("WeekRecords") == 3


def test_run_log_records(client, version):
    run = run_map(client, version)
    recs = log(client, run["run_id"])
    assert recs[0]["type"] == "config"
    calls = [r for r in recs if r["type"] == "call"]
    assert len(calls) == 4
    for r in calls:
        assert r["fingerprint"] and r["call_type"] in ("extractor", "orchestrator") and r["output"]
        assert r["usage"]["input_tokens"] > 0


def test_schema_failure_retried_then_fails_run(client, version):
    fake(client).handlers["WeekRecords"] = lambda m: {"concepts": [{"name": "x", "depth": "deep"}]}
    run = run_map(client, version)
    assert run["status"] == "failed" and "schema" in run["error"]
    assert fake(client).count("WeekRecords") == 3 * 3  # three weeks, three attempts each


def draft(client, vid):
    run_map(client, vid)
    m = client.get(f"/versions/{vid}/map").json()
    assert m["state"] == "draft"
    return m["concepts"]


def test_confirm_writes_map_and_rejects_unknown_evidence(client, version):
    concepts = draft(client, version)
    bad = json.loads(json.dumps(concepts))
    bad[0]["occurrences"][0]["evidence"].append("CS1010-w1-nope-p9")
    r = client.put(f"/versions/{version}/map", json={"concepts": bad})
    assert r.status_code == 422 and "CS1010-w1-nope-p9" in r.json()["detail"]
    assert client.put(f"/versions/{version}/map", json={"concepts": concepts}).status_code == 200
    m = client.get(f"/versions/{version}/map").json()
    assert m["state"] == "reviewed" and m["reviewed_at"]
    assert sorted(c["concept_id"] for c in m["concepts"]) == sorted(c["concept_id"] for c in concepts)


def stored(client, vid):
    from noodles import db
    return db.connect(client.app_runs.parent / "data" / "noodles.db")


def test_headings_follow_format(client, version):
    concepts = [{"concept_id": "CS1010:recursion", "name": "recursion", "aliases": ["recursive functions"],
                 "description": "", "occurrences": [{"week": 3, "depth": "explained", "evidence": ["CS1010-w3-week3-p1"]}]},
                {"concept_id": "CS1010:memoisation", "name": "memoisation", "aliases": [], "description": "",
                 "occurrences": [{"week": 3, "depth": "mentioned", "evidence": ["CS1010-w3-week3-p1"]}]}]
    assert client.put(f"/versions/{version}/map", json={"concepts": concepts}).status_code == 200
    heads = dict(stored(client, version).execute("SELECT passage_id, heading FROM passages").fetchall())
    assert heads["CS1010-w3-week3-p1"] == "[CS1010 | Week 3 | week3.pdf | Topics: memoisation; recursion (also: recursive functions)]"
    assert heads["CS1010-w1-week1-p1"] == "[CS1010 | Week 1 | week1.pdf]"


def test_fts_finds_alias_after_confirm(client, version):
    concepts = [{"concept_id": "CS1010:iteration", "name": "iteration", "aliases": ["looping"], "description": "",
                 "occurrences": [{"week": 2, "depth": "explained", "evidence": ["CS1010-w2-week2-p1"]}]}]
    client.put(f"/versions/{version}/map", json={"concepts": concepts})
    hits = stored(client, version).execute(
        "SELECT p.passage_id FROM passages_fts f JOIN passages p ON p.rowid = f.rowid WHERE passages_fts MATCH ?",
        ('"looping"',)).fetchall()
    assert [h[0] for h in hits] == ["CS1010-w2-week2-p1"]


def test_merge_rename_delete_edits_stored(client, version):
    c = {x["concept_id"]: x for x in draft(client, version)}
    a, b, gone = sorted(c)[:3]
    merged = dict(c[a], name="renamed topic", aliases=[c[b]["name"]],
                  occurrences=c[a]["occurrences"] + [o for o in c[b]["occurrences"]
                                                     if o["week"] not in {x["week"] for x in c[a]["occurrences"]}])
    rest = [x for k, x in c.items() if k not in (a, b, gone)]
    assert client.put(f"/versions/{version}/map", json={"concepts": [merged, *rest]}).status_code == 200
    m = {x["concept_id"]: x for x in client.get(f"/versions/{version}/map").json()["concepts"]}
    assert b not in m and gone not in m
    assert m[a]["name"] == "renamed topic" and m[a]["aliases"] == [c[b]["name"]]


def test_confirm_refused_while_map_run_running(client, version):
    import threading
    gate = threading.Event()
    f = fake(client)
    ok = f.handlers["MergedMap"]
    async def slow(m):
        while not gate.is_set():
            await asyncio.sleep(0.01)
        return ok(m)
    f.handlers["MergedMap"] = slow
    run = client.post(f"/versions/{version}/map-runs").json()["run_id"]
    try:
        assert client.put(f"/versions/{version}/map", json={"concepts": []}).status_code == 409
    finally:
        gate.set()
    assert wait_run(client, run)["status"] == "done"


def test_map_run_lists_its_steps(client, version):
    run = run_map(client, version)  # three weeks: one extraction per week, then the merge
    assert run["steps"] == ["Extract topics from week 1", "Extract topics from week 2", "Extract topics from week 3",
                            "Merge topics across weeks"]
    assert run["steps_done"] == 4
