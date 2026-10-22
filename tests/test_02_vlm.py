import io

import pytest
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from conftest import ingest
from noodles.ingest import flag_reasons, parse_pdfs

TEXT = "Loops repeat a block of code until a condition becomes false."


def pdf_with(tmp_path, draw) -> "Path":
    path = tmp_path / "x.pdf"
    c = canvas.Canvas(str(path))
    draw(c)
    c.showPage()
    c.save()
    return path


def text(c):
    c.drawString(72, 500, TEXT)


def image(c):
    text(c)
    buf = io.BytesIO()
    Image.new("RGB", (80, 80), (200, 30, 30)).save(buf, "PNG")
    c.drawImage(ImageReader(buf), 100, 200, 120, 120)


def drawing(c):
    text(c)
    for i in range(30):
        c.line(100 + i * 5, 100, 300, 300 + i * 3)


def short(c):
    c.drawString(72, 500, "Fig. 1")


def page(tmp_path, draw):
    pdf = pdf_with(tmp_path, draw)
    return parse_pdfs([pdf])[pdf][0]


def test_image_page_flagged_text_page_not(tmp_path):
    assert "image or table" in flag_reasons(page(tmp_path, image))
    assert flag_reasons(page(tmp_path, text)) == []


def test_little_text_flagged(tmp_path):
    assert "little text" in flag_reasons(page(tmp_path, short))


def test_garbled_text_flagged():
    garbled = {"text": "\ufffd\u2211\u222b \u2202\u221a\u2248 x = \ufffd\u2260\u2264 " * 6, "types": set(), "paths": 0}
    assert "garbled text" in flag_reasons(garbled)


def test_vector_drawing_flagged(tmp_path):
    assert "vector drawing" in flag_reasons(page(tmp_path, drawing))


@pytest.fixture
def two_pages():
    from conftest import make_pdf
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    text(c); c.showPage()
    image(c); c.showPage()
    c.save()
    return buf.getvalue()


def test_flagged_page_gets_vlm_text_others_keep_parser(client, two_pages):
    v = ingest(client, "CS1010", [("w1.pdf", two_pages)], {"w1.pdf": 1})
    p1, p2 = client.get(f"/versions/{v}/files").json()["files"][0]["pages"]
    assert p1["origin"] == "parser" and "Loops repeat" in p1["text"]
    assert p2["origin"] == "vlm" and p2["text"].startswith("[vlm]")


def test_ollama_unreachable_fails_and_writes_nothing(app, two_pages, tmp_path):
    from fastapi.testclient import TestClient

    from conftest import upload
    from noodles.api import create_app
    from noodles.ollama import Ollama

    bad = TestClient(create_app(tmp_path / "d2", tmp_path / "r2", ollama=Ollama(tmp_path / "t", "http://127.0.0.1:9")))
    up = upload(bad, "CS1010", [("w1.pdf", two_pages)])
    r = bad.post("/courses/CS1010/versions", json={"upload_id": up["upload_id"], "weeks": {"w1.pdf": 1}})
    assert r.status_code == 503 and "Ollama" in r.json()["detail"]
    assert bad.get("/courses").json() == []


def test_ollama_error_body_is_a_clear_error(monkeypatch, tmp_path):
    import httpx

    from noodles.ollama import Ollama, OllamaError
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200, json={"error": "model failed"},
                                                                       request=httpx.Request("POST", "http://x")))
    with pytest.raises(OllamaError):
        Ollama(tmp_path).transcribe(b"png")


def test_transcription_saved_per_page_and_reused(monkeypatch, tmp_path):
    import httpx

    from noodles.ollama import Ollama
    calls = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: calls.append(1) or httpx.Response(
        200, json={"response": "# Page"}, request=httpx.Request("POST", "http://x")))
    vlm = Ollama(tmp_path)
    assert vlm.transcribe(b"page-1") == "# Page"
    assert vlm.transcribe(b"page-1") == "# Page" and len(calls) == 1
    vlm.transcribe(b"page-2")
    assert len(calls) == 2


def test_transcription_cache_expires_after_ttl(monkeypatch, tmp_path):
    import os

    import httpx

    from noodles import ollama
    calls = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: calls.append(1) or httpx.Response(
        200, json={"response": "# Page"}, request=httpx.Request("POST", "http://x")))
    ollama.Ollama(tmp_path).transcribe(b"page")
    stale = ollama.time.time() - ollama.CACHE_TTL - 60
    for p in tmp_path.glob("*.md"):
        os.utime(p, (stale, stale))
    vlm = ollama.Ollama(tmp_path)
    assert list(tmp_path.glob("*.md")) == []  # pruned on start
    vlm.transcribe(b"page")
    assert len(calls) == 2


def ollama_replying(monkeypatch, tmp_path, **body):
    import httpx

    from noodles.ollama import Ollama
    calls = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: calls.append(1) or httpx.Response(
        200, json=body, request=httpx.Request("POST", "http://x")))
    return Ollama(tmp_path), calls


def test_code_fence_stripped(monkeypatch, tmp_path):
    vlm, _ = ollama_replying(monkeypatch, tmp_path, response="```markdown\n# Page\n\nText\n```", done_reason="stop")
    assert vlm.transcribe(b"page") == "# Page\n\nText"


def test_runaway_output_gives_none_and_is_cached(monkeypatch, tmp_path):
    vlm, calls = ollama_replying(monkeypatch, tmp_path, response="loop\n" * 500, done_reason="length")
    assert vlm.transcribe(b"page") is None
    assert vlm.transcribe(b"page") is None and len(calls) == 1


def test_page_without_vlm_text_keeps_parser_text(tmp_path, two_pages):
    from noodles.ingest import transcribe_flagged

    class Runaway:
        def transcribe(self, png):
            return None

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(two_pages)
    pages = parse_pdfs([pdf])[pdf]
    out = transcribe_flagged(pdf, pages, Runaway())
    assert [origin for _, origin in out] == ["parser", "parser"]
    assert out[1][0] == pages[1]["text"]


def test_confirm_reports_transcription_progress(tmp_path, two_pages):
    from fastapi.testclient import TestClient

    from conftest import upload
    from noodles.api import create_app
    seen = []

    class Spy:  # reads the progress endpoint while each flagged page is being transcribed
        def transcribe(self, png):
            seen.append(c.get(f"/progress/{up['upload_id']}").json())
            return "# Page"

    with TestClient(create_app(tmp_path / "d", tmp_path / "r", ollama=Spy())) as c:
        up = upload(c, "CS1010", [("w1.pdf", two_pages), ("w2.pdf", two_pages)])
        r = c.post("/courses/CS1010/versions", json={"upload_id": up["upload_id"], "weeks": {"w1.pdf": 1, "w2.pdf": 2}})
        assert r.status_code == 200
        # per file: pages transcribed out of that file's flagged pages; files are read in order
        assert seen == [{"w1.pdf": {"done": 0, "total": 1}, "w2.pdf": {"done": 0, "total": 1}},
                        {"w1.pdf": {"done": 1, "total": 1}, "w2.pdf": {"done": 0, "total": 1}}]
        assert c.get(f"/progress/{up['upload_id']}").json() == {
            "w1.pdf": {"done": 1, "total": 1}, "w2.pdf": {"done": 1, "total": 1}}


def test_page_image_is_served_as_png(client, two_pages):
    v = ingest(client, "CS1010", [("w1.pdf", two_pages)], {"w1.pdf": 1})
    slug = client.get(f"/versions/{v}/files").json()["files"][0]["slug"]
    r = client.get(f"/files/{v}/{slug}/pages/2.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content.startswith(b"\x89PNG")
    assert client.get(f"/files/{v}/{slug}/pages/3.png").status_code == 404


def test_edited_page_text_replaces_it_for_listing_and_search(client, two_pages):
    from noodles.student import recheck_search, student_conn
    v = ingest(client, "CS1010", [("w1.pdf", two_pages)], {"w1.pdf": 1})
    page = client.get(f"/versions/{v}/files").json()["files"][0]["pages"][1]
    r = client.put(f"/versions/{v}/passages/{page['passage_id']}", json={"text": "Recursion calls itself on a smaller input."})
    assert r.status_code == 200
    saved = client.get(f"/versions/{v}/files").json()["files"][0]["pages"][1]
    assert saved["text"] == "Recursion calls itself on a smaller input." and saved["origin"] == "vlm"
    hits = recheck_search(student_conn(client.app_db), "recursion smaller", v, 1, None)
    assert [h["passage_id"] for h in hits] == [page["passage_id"]]
    assert client.put(f"/versions/{v}/passages/nope", json={"text": "x"}).status_code == 404


def test_model_unloaded_after_every_fifth_transcribed_page(monkeypatch, tmp_path):
    import httpx

    from noodles.ollama import Ollama
    sent = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: sent.append(k["json"]) or httpx.Response(
        200, json={"response": "text", "done_reason": "stop"}, request=httpx.Request("POST", "http://x")))
    vlm = Ollama(tmp_path)
    vlm.transcribe(b"page 1")
    vlm.transcribe(b"page 1")  # cached: no model call, doesn't count
    for i in range(2, 12):
        vlm.transcribe(f"page {i}".encode())
    assert [i for i, j in enumerate(sent, 1) if j.get("keep_alive") == 0] == [5, 10]


def test_assessment_reading_reports_progress(tmp_path, two_pages):
    from fastapi.testclient import TestClient

    from conftest import ingest
    from noodles.api import create_app
    from noodles.fakes import FakeOpenAI
    seen = []

    class Spy:  # reads the progress endpoint while each flagged page of the paper and answers is transcribed
        def transcribe(self, png):
            seen.append(c.get("/progress/p1").json())
            return "# Page"

    with TestClient(create_app(tmp_path / "d", tmp_path / "r", ollama=Spy(), openai=FakeOpenAI())) as c:
        v = ingest(c, "CS1010", [("w1.pdf", two_pages)], {"w1.pdf": 1})
        seen.clear()
        r = c.post(f"/versions/{v}/assessments", data={"name": "Quiz", "week_cutoff": 1, "current_format": "online_quiz", "progress_id": "p1"},
                   files=[("paper", ("Quiz.pdf", two_pages)), ("answers", ("Ans.pdf", two_pages))])
        assert r.status_code == 200, r.text
        assert seen == [{"Quiz.pdf": {"done": 0, "total": 1}}, {"Quiz.pdf": {"done": 1, "total": 1}, "Ans.pdf": {"done": 0, "total": 1}}]


def test_adding_files_reports_progress(tmp_path, two_pages):
    from fastapi.testclient import TestClient

    from conftest import ingest, upload
    from noodles.api import create_app
    seen = []

    class Spy:  # reads the progress endpoint while each flagged page of the added file is transcribed
        def transcribe(self, png):
            if adding:
                seen.append(c.get(f"/progress/{up['upload_id']}").json())
            return "# Page"

    adding = False
    with TestClient(create_app(tmp_path / "d", tmp_path / "r", ollama=Spy())) as c:
        v = ingest(c, "CS1010", [("w1.pdf", two_pages)], {"w1.pdf": 1})
        up = upload(c, "CS1010", [("w2.pdf", two_pages)])
        adding = True
        assert c.post(f"/versions/{v}/files", json={"upload_id": up["upload_id"], "weeks": {"w2.pdf": 2}}).status_code == 200
        assert seen == [{"w2.pdf": {"done": 0, "total": 1}}]
