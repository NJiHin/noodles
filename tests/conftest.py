"""Shared fixtures: synthetic PDFs and Office files, and an app on a temp data dir."""
import io
import time

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from noodles.api import create_app
from noodles.fakes import FakeOllama, FakeOpenAI


def make_pdf(pages: list[str]) -> bytes:
    """One PDF page per string, text drawn mid-page."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for text in pages:
        for i, line in enumerate(text.split("\n")):
            c.drawString(72, 500 - 16 * i, line)
        c.showPage()
    c.save()
    return buf.getvalue()


def make_docx(paragraphs: list[str]) -> bytes:
    from docx import Document

    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def app(tmp_path):
    return create_app(data_dir=tmp_path / "data", runs_dir=tmp_path / "runs", ollama=FakeOllama(),
                      openai=FakeOpenAI(), llm_opts={"retry_delay": 0})


@pytest.fixture
def client(app):
    with TestClient(app) as c:  # one event loop for the app's lifetime, so background runs keep going
        c.app_db = app.state.db_path
        yield c


def wait_run(client, run_id, timeout=20):
    """Poll a background run until it stops running; returns its status."""
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/runs/{run_id}").json()
        if r["status"] != "running":
            return r
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} still running")


def upload(client, code, files):
    """files: list of (filename, bytes). Returns the upload response JSON."""
    r = client.post(f"/courses/{code}/uploads", files=[("files", (n, b)) for n, b in files])
    assert r.status_code == 200, r.text
    return r.json()


def ingest(client, code, files, weeks):
    """Upload then confirm with weeks {filename: week}. Returns version_id."""
    up = upload(client, code, files)
    r = client.post(f"/courses/{code}/versions", json={"upload_id": up["upload_id"], "weeks": weeks})
    assert r.status_code == 200, r.text
    return r.json()["version_id"]
