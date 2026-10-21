"""Adding files to a course: the latest version changes in place (sys-design Stage 0, "Adding files to a course")."""
import pytest

from conftest import ingest, make_pdf, upload, wait_run
from test_05_student import assess, course, drive

L1 = [f"Lecture one page {i} covers variables and the values they hold." for i in (1, 2)]
L2 = ["Lecture two covers loops that repeat a block of code."]
P1, P2 = make_pdf(L1), make_pdf(L2)  # built once: reportlab stamps each build, and fingerprints hash the bytes


def add(client, vid, files, weeks):
    up = upload(client, "CS1010", files)
    return client.post(f"/versions/{vid}/files", json={"upload_id": up["upload_id"], "weeks": weeks})


@pytest.fixture
def vid(client):
    return ingest(client, "CS1010", [("Lecture1.pdf", P1)], {"Lecture1.pdf": 1})


def pages(client, vid):
    return {p["passage_id"]: p["text"] for f in client.get(f"/versions/{vid}/files").json()["files"] for p in f["pages"]}


def test_added_file_joins_the_version_and_the_rest_stays(client, vid):
    client.put(f"/versions/{vid}/passages/CS1010-w1-lecture1-p1", json={"text": "Corrected by hand."})
    r = add(client, vid, [("Lecture2.pdf", P2)], {"Lecture2.pdf": 2})
    assert r.status_code == 200, r.text
    assert r.json()["version_id"] == vid
    p = pages(client, vid)
    assert p["CS1010-w1-lecture1-p1"] == "Corrected by hand."
    assert "loops" in p["CS1010-w2-lecture2-p1"]
    v = client.get(f"/versions/{vid}").json()
    assert v["materials_changed_at"] and v["added_files"] == [{"filename": "Lecture2.pdf", "week": 2}]
    assert client.get("/courses").json()[0]["versions"][0]["id"] == vid  # no new version


def test_same_name_replaces_the_file_and_its_corrections(client, vid):
    client.put(f"/versions/{vid}/passages/CS1010-w1-lecture1-p1", json={"text": "Corrected by hand."})
    r = add(client, vid, [("Lecture1.pdf", make_pdf(["Lecture one, revised: only one page about constants."]))], {"Lecture1.pdf": 1})
    assert r.status_code == 200, r.text
    assert list(pages(client, vid).values()) == ["Lecture one, revised: only one page about constants."]


def test_replaced_file_drops_map_evidence_on_pages_that_are_gone(client, vid):
    concept = {"concept_id": "CS1010:variables", "name": "Variables", "aliases": [], "description": "",
               "occurrences": [{"week": 1, "depth": "explained", "evidence": ["CS1010-w1-lecture1-p1", "CS1010-w1-lecture1-p2"]}]}
    assert client.put(f"/versions/{vid}/map", json={"concepts": [concept]}).status_code == 200
    add(client, vid, [("Lecture1.pdf", make_pdf(["Lecture one, revised."]))], {"Lecture1.pdf": 1})
    [c] = client.get(f"/versions/{vid}/map").json()["concepts"]
    assert c["occurrences"][0]["evidence"] == ["CS1010-w1-lecture1-p1"]


def test_later_upload_of_the_same_files_finds_the_version(client, vid):
    add(client, vid, [("Lecture2.pdf", P2)], {"Lecture2.pdf": 2})
    again = ingest(client, "CS1010", [("Lecture1.pdf", P1), ("Lecture2.pdf", P2)],
                   {"Lecture1.pdf": 1, "Lecture2.pdf": 2})
    assert again == vid
    alone = ingest(client, "CS1010", [("Lecture1.pdf", P1)], {"Lecture1.pdf": 1})
    assert alone != vid  # Lecture1 alone no longer names the changed version


def test_add_matching_another_version_is_refused(client, vid):
    other = ingest(client, "CS1010", [("Lecture1.pdf", P1), ("Lecture2.pdf", P2)],
                   {"Lecture1.pdf": 1, "Lecture2.pdf": 2})
    r = add(client, vid, [("Lecture2.pdf", P2)], {"Lecture2.pdf": 2})
    assert r.status_code == 409 and other in r.json()["detail"]
    assert "CS1010-w2-lecture2-p1" not in pages(client, vid)


def test_unconfirmed_week_refused(client, vid):
    assert add(client, vid, [("Lecture2.pdf", P2)], {}).status_code == 422


def test_map_outdated_until_rebuilt_and_confirmed(client):
    vid = course(client, "CS1010", {1: "Variables store values that a program can read."})
    assert client.get(f"/versions/{vid}").json()["outdated"] == {"map": False, "map_confirmed": True, "results": False}
    add(client, vid, [("week2.pdf", P2)], {"week2.pdf": 2})
    assert client.get(f"/versions/{vid}").json()["outdated"] == {"map": True, "map_confirmed": False, "results": False}
    wait_run(client, client.post(f"/versions/{vid}/map-runs").json()["run_id"])
    assert client.get(f"/versions/{vid}").json()["outdated"]["map"] is False
    concepts = client.get(f"/versions/{vid}/map").json()["concepts"]
    client.put(f"/versions/{vid}/map", json={"concepts": concepts})
    assert client.get(f"/versions/{vid}").json()["outdated"]["map_confirmed"] is True


def test_results_outdated_until_test_drive_reruns(client):
    vid = course(client, "CS2030", {1: "Variables store values.", 2: "Loops repeat a block of code."})
    assess(client, vid)
    drive(client, vid)
    add(client, vid, [("extra.pdf", make_pdf(["Extra notes on loops."]))], {"extra.pdf": 2})
    assert client.get(f"/versions/{vid}").json()["outdated"]["results"] is True
    drive(client, vid)
    assert client.get(f"/versions/{vid}").json()["outdated"]["results"] is False


def test_map_rebuild_after_adding_reuses_this_versions_topic_ids(client, vid):
    concept = {"concept_id": "CS1010:variables", "name": "Variables", "aliases": [], "description": "",
               "occurrences": [{"week": 1, "depth": "explained", "evidence": ["CS1010-w1-lecture1-p1"]}]}
    client.put(f"/versions/{vid}/map", json={"concepts": [concept]})
    add(client, vid, [("Lecture2.pdf", P2)], {"Lecture2.pdf": 2})
    run = wait_run(client, client.post(f"/versions/{vid}/map-runs").json()["run_id"])
    assert run["status"] == "done"
    calls = [m for s, _, m, _ in client.app.state.openai.calls if s == "MergedMap"]
    assert "CS1010:variables" in calls[-1][-1]["content"]  # the merge sees this version's confirmed topics
