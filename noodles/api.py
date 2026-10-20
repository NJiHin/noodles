"""FastAPI app. Run: uv run uvicorn --factory noodles.api:from_env --reload"""
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from noodles import db
from noodles.ollama import Ollama, OllamaError
from noodles.ingest import IngestError, check_upload_name, guess_week, ingest

ID = re.compile(r"^[A-Za-z0-9_-]+$")


class ConfirmWeeks(BaseModel):
    upload_id: str
    weeks: dict[str, int]


def create_app(data_dir: Path, runs_dir: Path, ollama=None) -> FastAPI:
    data_dir, runs_dir = Path(data_dir), Path(runs_dir)
    db_path, files_dir, uploads_dir = data_dir / "noodles.db", data_dir / "files", data_dir / "uploads"
    db.init(db_path)
    vlm = ollama or Ollama()
    app = FastAPI(title="noodles")

    @contextmanager
    def conn():
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    def safe_id(value: str) -> str:
        if not ID.match(value):
            raise HTTPException(400, f"invalid id: {value}")
        return value

    @app.get("/courses")
    def courses():
        with conn() as c:
            rows = c.execute("SELECT * FROM versions ORDER BY course_code, created_at DESC").fetchall()
        out: dict[str, list] = {}
        for r in rows:
            out.setdefault(r["course_code"], []).append(dict(r))
        return [{"code": k, "versions": v} for k, v in out.items()]

    @app.post("/courses/{code}/uploads")
    def upload(code: str, files: list[UploadFile]):
        safe_id(code)
        names = [Path(f.filename or "").name for f in files]
        if not names:
            raise HTTPException(400, "upload at least one file")
        try:
            for n in names:
                check_upload_name(n)
        except IngestError as e:
            raise HTTPException(400, str(e))
        if len(set(names)) != len(names):
            raise HTTPException(400, "two uploaded files have the same filename")
        upload_id = uuid.uuid4().hex
        d = uploads_dir / upload_id
        d.mkdir(parents=True)
        for i, (f, n) in enumerate(zip(files, names)):
            # one subdir per file: names differing only in case collide on macOS
            (d / str(i)).mkdir()
            (d / str(i) / n).write_bytes(f.file.read())
        return {"upload_id": upload_id, "files": [{"filename": n, "week_guess": guess_week(n)} for n in names]}

    @app.post("/courses/{code}/versions")
    def confirm(code: str, body: ConfirmWeeks):
        safe_id(code)
        d = uploads_dir / safe_id(body.upload_id)
        if not d.is_dir():
            raise HTTPException(404, "upload not found")
        staged = sorted(d.glob("*/*"), key=lambda p: int(p.parent.name))
        missing = [p.name for p in staged if p.name not in body.weeks]
        if set(body.weeks) - {p.name for p in staged}:
            raise HTTPException(422, "weeks given for files that weren't uploaded")
        if missing or any(w < 1 for w in body.weeks.values()):
            raise HTTPException(422, f"confirm a week (1 or more) for every file: {', '.join(missing)}")
        with conn() as c:
            try:
                return {"version_id": ingest(c, files_dir, code, staged, body.weeks, vlm)}
            except IngestError as e:
                raise HTTPException(422, str(e))
            except OllamaError as e:
                raise HTTPException(503, str(e))

    @app.get("/versions/{vid}/files")
    def version_files(vid: str):
        with conn() as c:
            v = c.execute("SELECT * FROM versions WHERE id = ?", (vid,)).fetchone()
            if not v:
                raise HTTPException(404, "version not found")
            files = c.execute("SELECT slug, filename, week FROM files WHERE version_id = ? ORDER BY week, filename",
                              (vid,)).fetchall()
            out = []
            for f in files:
                pages = c.execute("SELECT passage_id, page, text, origin FROM passages "
                                  "WHERE version_id = ? AND file_slug = ? ORDER BY page", (vid, f["slug"])).fetchall()
                out.append({**dict(f), "pages": [dict(p) for p in pages]})
        return {"version_id": vid, "course_code": v["course_code"], "created_at": v["created_at"], "files": out}

    @app.get("/files/{vid}/{slug}.pdf")
    def source_pdf(vid: str, slug: str):
        path = files_dir / safe_id(vid) / f"{safe_id(slug)}.pdf"
        if not path.exists():
            raise HTTPException(404, "file not found")
        return FileResponse(path, media_type="application/pdf")

    return app


def from_env() -> FastAPI:
    """NOODLES_DATA / NOODLES_RUNS dirs; NOODLES_FAKE=1 swaps in fake model clients (no model calls)."""
    fake = os.environ.get("NOODLES_FAKE") == "1"
    if fake:
        from noodles.fakes import FakeOllama
    return create_app(Path(os.environ.get("NOODLES_DATA", "data")), Path(os.environ.get("NOODLES_RUNS", "runs")),
                      ollama=FakeOllama() if fake else None)
