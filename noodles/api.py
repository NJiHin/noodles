"""FastAPI app. Run: uv run uvicorn --factory noodles.api:from_env --reload"""
import asyncio
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from noodles import db
from noodles.coursemap import Concept, MapError, build_map, load_map, save_map
from noodles.llm import OpenAIClient, Run, find_log, read_log
from noodles.ollama import Ollama, OllamaError
from noodles.ingest import IngestError, check_upload_name, guess_week, ingest

ID = re.compile(r"^[A-Za-z0-9_-]+$")


class MapBody(BaseModel):
    concepts: list[Concept]


class ConfirmWeeks(BaseModel):
    upload_id: str
    weeks: dict[str, int]


def create_app(data_dir: Path, runs_dir: Path, ollama=None, openai=None, llm_opts: dict | None = None) -> FastAPI:
    """openai: a client with `async complete(model, messages, schema)`; default is the real OpenAI client."""
    data_dir, runs_dir = Path(data_dir), Path(runs_dir)
    db_path, files_dir, uploads_dir = data_dir / "noodles.db", data_dir / "files", data_dir / "uploads"
    db.init(db_path)
    vlm = ollama or Ollama()
    app = FastAPI(title="noodles")
    app.state.openai = openai
    tasks: dict[str, asyncio.Task] = {}

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

    def version_row(c, vid: str):
        v = c.execute("SELECT * FROM versions WHERE id = ?", (vid,)).fetchone()
        if not v:
            raise HTTPException(404, "version not found")
        return v

    def start_job(code: str, vid: str, config: dict, work) -> str:
        """Run `work(run, conn)` as a background task; its run log reports progress."""
        run = Run.start(runs_dir, code, vid, config, openai or OpenAIClient(), **(llm_opts or {}))

        async def job():
            c = db.connect(db_path)
            try:
                await work(run, c)
                run.end()
            except Exception as e:
                run.end(str(e) or type(e).__name__)
            finally:
                c.close()

        tasks[run.id] = asyncio.create_task(job())
        return run.id

    def run_status(path: Path) -> dict:
        recs = read_log(path)
        cfg, end = recs[0], recs[-1] if recs[-1]["type"] == "end" else None
        calls = [r for r in recs if r["type"] == "call"]
        task = tasks.get(cfg["run_id"])
        status = end["status"] if end else "running" if task and not task.done() else "interrupted"
        out = {"run_id": cfg["run_id"], "kind": cfg["kind"], "version": cfg["version"], "status": status,
               "error": end and end["error"], "started_at": cfg["started_at"], "ended_at": end and end["ended_at"],
               "done": len(calls), "total": None, "stage": ""}
        if cfg["kind"] == "map":
            n = len(cfg["weeks"])
            extracted = sum(r["call_type"] == "extractor" for r in calls)
            out |= {"total": n + 1, "stage": f"Extracting topics, week {min(extracted + 1, n)} of {n}" if extracted < n
                    else "Merging topics across weeks"}
        return out

    def latest_run(code: str, vid: str, kind: str) -> Path | None:
        for path in sorted((runs_dir / code / vid).glob("*.jsonl"), reverse=True):
            if read_log(path)[0]["kind"] == kind:
                return path
        return None

    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        path = find_log(runs_dir, safe_id(run_id))
        if not path:
            raise HTTPException(404, "run not found")
        return run_status(path)

    @app.post("/versions/{vid}/map-runs")
    async def start_map_run(vid: str):
        with conn() as c:
            v = version_row(c, vid)
            weeks = [r[0] for r in c.execute("SELECT DISTINCT week FROM passages WHERE version_id = ? ORDER BY week", (vid,))]
        code = v["course_code"]
        return {"run_id": start_job(code, vid, {"kind": "map", "weeks": weeks},
                                    lambda run, c: build_map(run, c, code, vid))}

    @app.get("/versions/{vid}/map")
    def get_map(vid: str):
        """The reviewed map, or the latest run's draft if it is newer. Includes passage locations for links."""
        with conn() as c:
            v = version_row(c, vid)
            reviewed = load_map(c, vid) if v["map_reviewed_at"] else None
            passages = {r["passage_id"]: {"slug": r["file_slug"], "page": r["page"], "week": r["week"]}
                        for r in c.execute("SELECT passage_id, file_slug, page, week FROM passages WHERE version_id = ?", (vid,))}
        path = latest_run(v["course_code"], vid, "map")
        run = run_status(path) if path else None
        draft = next((r["map"]["concepts"] for r in read_log(path) if r["type"] == "draft"), None) if path else None
        if draft is not None and run["status"] == "done" and (not reviewed or run["ended_at"] > v["map_reviewed_at"]):
            state, concepts = "draft", draft
        elif reviewed is not None:
            state, concepts = "reviewed", reviewed
        else:
            state, concepts = "none", []
        return {"version_id": vid, "course_code": v["course_code"], "state": state,
                "reviewed_at": v["map_reviewed_at"], "run": run, "concepts": concepts, "passages": passages}

    @app.put("/versions/{vid}/map")
    def confirm_map(vid: str, body: MapBody):
        with conn() as c:
            v = version_row(c, vid)
            path = latest_run(v["course_code"], vid, "map")
            if path and run_status(path)["status"] == "running":
                raise HTTPException(409, "the map is still being built; confirm once it finishes")
            try:
                save_map(c, vid, body.concepts)
            except MapError as e:
                raise HTTPException(422, str(e))
        return {"ok": True}

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
            v = version_row(c, vid)
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
        from noodles.fakes import FakeOllama, FakeOpenAI
    return create_app(Path(os.environ.get("NOODLES_DATA", "data")), Path(os.environ.get("NOODLES_RUNS", "runs")),
                      ollama=FakeOllama() if fake else None, openai=FakeOpenAI() if fake else None)
