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
