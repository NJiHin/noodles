import pytest

from conftest import ingest, make_docx, make_pdf, upload
from noodles.ingest import guess_week


@pytest.mark.parametrize("name", ["old.ppt", "old.doc"])
def test_legacy_office_rejected_with_resave_message(client, name):
    r = client.post("/courses/CS1010/uploads", files=[("files", (name, b"x"))])
    assert r.status_code == 400
    assert "re-save" in r.json()["detail"]


def test_pdf_pptx_docx_accepted(client):
    up = upload(client, "CS1010", [("a.pdf", make_pdf(["x"])), ("b.pptx", b"x"), ("c.docx", b"x")])
    assert [f["filename"] for f in up["files"]] == ["a.pdf", "b.pptx", "c.docx"]


@pytest.mark.parametrize("name,week", [
    ("Week05_Recursion.pptx", 5),
    ("L3-loops.pdf", 3),
    ("lecture-notes.pdf", None),
])
def test_week_guess(name, week):
    assert guess_week(name) == week


def test_week_guess_returned_by_upload(client):
    up = upload(client, "CS1010", [("Week05_Recursion.pdf", make_pdf(["x"]))])
    assert up["files"][0]["week_guess"] == 5


def test_same_slug_files_get_distinct_slugs(client):
    v = ingest(client, "CS1010", [("notes.pdf", make_pdf(["a"])), ("Notes.pdf", make_pdf(["b"]))],
               {"notes.pdf": 1, "Notes.pdf": 1})
    slugs = [f["slug"] for f in client.get(f"/versions/{v}/files").json()["files"]]
    assert len(set(slugs)) == 2


def test_three_page_pdf_gives_three_parser_passages(client):
    v = ingest(client, "CS1010", [("slides.pdf", make_pdf(["page one", "page two", "page three"]))],
               {"slides.pdf": 5})
    f = client.get(f"/versions/{v}/files").json()["files"][0]
    assert [p["passage_id"] for p in f["pages"]] == [f"CS1010-w5-slides-p{i}" for i in (1, 2, 3)]
    assert {p["origin"] for p in f["pages"]} == {"parser"}
    assert "page two" in f["pages"][1]["text"]


def test_version_id_is_fingerprint_of_files_and_weeks(client):
    files = [("a.pdf", make_pdf(["a"])), ("b.pdf", make_pdf(["b"]))]
    v1 = ingest(client, "CS1010", files, {"a.pdf": 1, "b.pdf": 2})
    v2 = ingest(client, "CS1010", files, {"a.pdf": 1, "b.pdf": 2})
    v3 = ingest(client, "CS1010", files, {"a.pdf": 1, "b.pdf": 3})
    assert v1 == v2 != v3


def test_stored_pdf_served_and_page_count_matches(client):
    v = ingest(client, "CS1010", [("slides.pdf", make_pdf(["1", "2", "3"]))], {"slides.pdf": 5})
    r = client.get(f"/files/{v}/slides.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    import pypdfium2
    assert len(pypdfium2.PdfDocument(r.content)) == len(client.get(f"/versions/{v}/files").json()["files"][0]["pages"])


def test_docx_converted_to_pdf_before_parsing(client):
    v = ingest(client, "CS1010", [("Week2_notes.docx", make_docx(["Loops repeat a block of code."]))],
               {"Week2_notes.docx": 2})
    f = client.get(f"/versions/{v}/files").json()["files"][0]
    assert "Loops repeat" in f["pages"][0]["text"]
    assert client.get(f"/files/{v}/{f['slug']}.pdf").content.startswith(b"%PDF")


def test_unconfirmed_week_rejected(client):
    up = upload(client, "CS1010", [("notes.pdf", make_pdf(["a"]))])
    r = client.post("/courses/CS1010/versions", json={"upload_id": up["upload_id"], "weeks": {}})
    assert r.status_code == 422


def test_courses_lists_versions(client):
    v = ingest(client, "CS1010", [("a.pdf", make_pdf(["a"]))], {"a.pdf": 1})
    assert [x["id"] for x in client.get("/courses").json()[0]["versions"]] == [v]


def test_week_for_file_not_uploaded_rejected(client):
    up = upload(client, "CS1010", [("notes.pdf", make_pdf(["a"]))])
    r = client.post("/courses/CS1010/versions",
                    json={"upload_id": up["upload_id"], "weeks": {"notes.pdf": 1, "gone.pdf": 2}})
    assert r.status_code == 422
