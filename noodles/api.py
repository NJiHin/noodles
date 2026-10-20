"""FastAPI app. Run: uv run uvicorn --factory noodles.api:from_env --reload"""
import asyncio
import json
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import shutil
import tempfile

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from noodles import db
from noodles.assessments import FORMATS, QuestionsError, SplitQuestion, confirmed_questions, flags, save_questions, split
from noodles.coursemap import Concept, MapError, build_map, load_map, save_map
from noodles.llm import OpenAIClient, Run, find_log, now, read_log
from noodles.ollama import Ollama, OllamaError
from noodles.student import test_drive
from noodles.web import Verdict, exposure
from noodles.report import learning_path, recommend, summary
from noodles.ingest import IngestError, check_upload_name, guess_week, ingest, read_document, slugify

ID = re.compile(r"^[A-Za-z0-9_-]+$")


class QuestionsBody(BaseModel):
    questions: list[SplitQuestion]


class MapBody(BaseModel):
    concepts: list[Concept]


class TestDriveBody(BaseModel):
    prerequisite: str | None = None  # course code; its latest reviewed version is used


class DecisionBody(BaseModel):
    claim: str
    decision: Literal["accepted", "rejected"]


class OverrideBody(BaseModel):
    verdict: Verdict


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
    app.state.openai, app.state.db_path = openai, db_path
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
        if cfg["kind"] == "split":
            out |= {"total": 1, "stage": "Splitting the paper into questions"}
        if cfg["kind"] == "map":
            n = len(cfg["weeks"])
            extracted = sum(r["call_type"] == "extractor" for r in calls)
            out |= {"total": n + 1, "stage": f"Extracting topics, week {min(extracted + 1, n)} of {n}" if extracted < n
                    else "Merging topics across weeks"}
        if cfg["kind"] == "test_drive":
            answered = sum(r["type"] == "answer" for r in recs)
            out |= {"done": answered, "total": len(cfg["questions"]),
                    "stage": f"Student answering, {answered} of {len(cfg['questions'])} questions"}
        return out

    def latest_run(code: str, vid: str, kind: str, **match) -> Path | None:
        for path in sorted((runs_dir / code / vid).glob("*.jsonl"), reverse=True):
            cfg = read_log(path)[0]
            if cfg["kind"] == kind and all(cfg.get(k) == v for k, v in match.items()):
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

    @app.post("/versions/{vid}/assessments")
    async def add_assessment(vid: str, name: str = Form(), week_cutoff: int = Form(), current_format: str = Form(),
                             paper: UploadFile = Form(), answers: UploadFile | None = Form(None)):
        """Parse the paper (and answers) into assessment_files, then start the question split."""
        if week_cutoff < 1 or current_format not in FORMATS:
            raise HTTPException(422, f"week_cutoff must be 1 or more and current_format one of {', '.join(FORMATS)}")
        aid = slugify(name)
        with conn() as c:
            code = version_row(c, vid)["course_code"]
        texts = {}
        with tempfile.TemporaryDirectory() as tmp:
            for kind, f in (("paper", paper), ("answers", answers)):
                if not f:
                    continue
                fname = Path(f.filename or "").name
                try:
                    check_upload_name(fname)
                    src = Path(tmp) / kind / fname
                    src.parent.mkdir()
                    src.write_bytes(await f.read())
                    texts[kind] = (fname, await asyncio.to_thread(read_document, src, vlm))
                except IngestError as e:
                    raise HTTPException(422, str(e))
                except OllamaError as e:
                    raise HTTPException(503, str(e))
        with conn() as c, c:
            before = {(r["kind"], r["filename"], r["text"]) for r in c.execute(
                "SELECT kind, filename, text FROM assessment_files WHERE version_id = ? AND assessment_id = ?", (vid, aid))}
            if before != {(k, fn, t) for k, (fn, t) in texts.items()}:  # new files: confirmed questions no longer apply
                c.execute("DELETE FROM questions WHERE version_id = ? AND assessment_id = ?", (vid, aid))
            c.execute("DELETE FROM assessment_files WHERE version_id = ? AND assessment_id = ?", (vid, aid))
            c.execute("INSERT OR REPLACE INTO assessments (version_id, assessment_id, week_cutoff, current_format) "
                      "VALUES (?, ?, ?, ?)", (vid, aid, week_cutoff, current_format))
            c.executemany("INSERT INTO assessment_files (version_id, assessment_id, kind, filename, text) VALUES (?, ?, ?, ?, ?)",
                          [(vid, aid, k, fn, t) for k, (fn, t) in texts.items()])
        paper_text, answers_text = texts["paper"][1], texts.get("answers", (None, None))[1]
        run_id = start_job(code, vid, {"kind": "split", "assessment_id": aid},
                           lambda run, c: split(run, aid, paper_text, answers_text))
        return {"assessment_id": aid, "run_id": run_id}

    @app.get("/versions/{vid}/assessments")
    def list_assessments(vid: str):
        """Each assessment with its confirmed questions, or else the latest split draft; code-check flags on each."""
        out = []
        with conn() as c:
            code = version_row(c, vid)["course_code"]
            for a in c.execute("SELECT * FROM assessments WHERE version_id = ? ORDER BY week_cutoff, assessment_id", (vid,)):
                aid = a["assessment_id"]
                files = {r["kind"]: r for r in c.execute("SELECT kind, filename, text FROM assessment_files "
                                                         "WHERE version_id = ? AND assessment_id = ?", (vid, aid))}
                path = latest_run(code, vid, "split", assessment_id=aid)
                run = run_status(path) if path else None
                draft = next((r for r in read_log(path) if r["type"] == "split"), None) if path else None
                questions = confirmed_questions(c, vid, aid)
                state = "confirmed" if questions else "draft" if draft else run["status"] if run else "none"
                if not questions and draft:
                    questions = draft["questions"]
                paper = files["paper"]["text"] if "paper" in files else ""
                out.append({"assessment_id": aid, "week_cutoff": a["week_cutoff"], "current_format": a["current_format"],
                            "files": {k: r["filename"] for k, r in files.items()}, "state": state, "run": run,
                            "questions": [{**q, "flags": flags(paper, q)} for q in questions],
                            "unmatched_marking_material": draft["unmatched_marking_material"] if draft and state == "draft" else []})
        return out

    @app.put("/versions/{vid}/assessments/{aid}/questions")
    def confirm_questions(vid: str, aid: str, body: QuestionsBody):
        with conn() as c:
            version_row(c, vid)
            if not c.execute("SELECT 1 FROM assessments WHERE version_id = ? AND assessment_id = ?", (vid, aid)).fetchone():
                raise HTTPException(404, "assessment not found")
            try:
                save_questions(c, vid, aid, body.questions)
            except QuestionsError as e:
                raise HTTPException(422, str(e))
        return {"ok": True}

    @app.post("/versions/{vid}/test-drives")
    async def start_test_drive(vid: str, body: TestDriveBody):
        """The student on every confirmed non-code question. Needs a reviewed map and confirmed questions."""
        with conn() as c:
            v = version_row(c, vid)
            if not v["map_reviewed_at"]:
                raise HTTPException(409, "confirm the course map first")
            questions = [{**dict(r), "options": json.loads(r["options"]) if r["options"] else None} for r in c.execute(
                "SELECT q.question_id, q.text, q.options, q.type, q.marking_material, a.week_cutoff FROM questions q JOIN assessments a ON "
                "a.version_id = q.version_id AND a.assessment_id = q.assessment_id WHERE q.version_id = ? "
                "AND q.type != 'code' ORDER BY a.week_cutoff, q.rowid", (vid,))]
            if not questions:
                raise HTTPException(409, "confirm the questions of at least one assessment first")
            prereq = None
            if body.prerequisite:
                p = c.execute("SELECT id FROM versions WHERE course_code = ? AND map_reviewed_at IS NOT NULL "
                              "ORDER BY created_at DESC LIMIT 1", (body.prerequisite,)).fetchone()
                if not p or body.prerequisite == v["course_code"]:
                    raise HTTPException(422, f"{body.prerequisite} has no version with a reviewed map")
                prereq = p["id"]
        code = v["course_code"]
        config = {"kind": "test_drive", "target": vid, "prerequisite": prereq, "prerequisite_course": body.prerequisite,
                  "questions": [q["question_id"] for q in questions]}
        return {"run_id": start_job(code, vid, config, lambda run, c: test_drive(
            run, db_path, code, vid, prereq, body.prerequisite, questions))}

    @app.get("/versions/{vid}/summary")
    def get_summary(vid: str):
        r = get_review(vid)
        return {"course_code": r["course_code"], "run": r["run"], **summary(r["questions"])}

    @app.get("/versions/{vid}/learning-path")
    def get_learning_path(vid: str):
        r = get_review(vid)
        with conn() as c:
            concepts = load_map(c, vid)
        lp = learning_path(concepts, r["questions"])
        return {"course_code": r["course_code"], "run": r["run"], **lp,
                "assessments": [{"assessment_id": a, "week_cutoff": w} for a, w in lp["assessments"]]}

    @app.get("/versions/{vid}/review")
    def get_review(vid: str):
        """Every confirmed question with the latest test-drive's student output; cited passages resolved for links."""
        with conn() as c:
            code = version_row(c, vid)["course_code"]
            path = latest_run(code, vid, "test_drive")
            recs = read_log(path) if path else []
            answers = {r["question_id"]: r for r in recs if r["type"] == "answer"}
            cfg = recs[0] if recs else {}
            decisions = {r["id"]: dict(r) for r in c.execute("SELECT * FROM assumed_knowledge WHERE course_code = ?", (code,))}
            overrides = {(r["question_id"], r["agent"]): r["verdict"] for r in c.execute(
                "SELECT * FROM verdict_overrides WHERE run_id = ?", (cfg.get("run_id"),))}
            cited = {e for a in answers.values() for s in a["steps"] for e in s["evidence"]}
            passages = {r["passage_id"]: dict(r) for r in c.execute(
                f"SELECT p.passage_id, v.course_code AS course, p.version_id, p.week, f.filename, p.file_slug AS slug, "
                f"p.page, p.text FROM passages p JOIN versions v ON v.id = p.version_id JOIN files f ON "
                f"f.version_id = p.version_id AND f.slug = p.file_slug WHERE p.version_id IN (?, ?) "
                f"AND p.passage_id IN ({','.join('?' * len(cited))})", (vid, cfg.get("prerequisite"), *cited))}
            questions = []
            for q in c.execute("SELECT q.question_id, q.assessment_id, q.text, q.options, q.type, a.week_cutoff, "
                               "a.current_format FROM questions q JOIN assessments a ON a.version_id = q.version_id AND "
                               "a.assessment_id = q.assessment_id WHERE q.version_id = ? ORDER BY a.week_cutoff, "
                               "q.assessment_id, q.rowid", (vid,)):
                a = answers.get(q["question_id"])
                def seen(e):  # a cited ID outside the week limit stays visible, unresolved
                    p = passages.get(e)
                    ok = p and (p["version_id"] == cfg["prerequisite"] or p["week"] <= q["week_cutoff"])
                    return p if ok else {"passage_id": e}
                if a:
                    g = {x["step_id"]: x for x in a.get("grounding", [])}
                    a = {**{k: v for k, v in a.items() if k != "grounding"},
                         "steps": [{**s, "evidence": [seen(e) for e in s["evidence"]], "grounding": g.get(s["step_id"]),
                                    "assumption": assumption(s, decisions)} for s in a["steps"]]}
                marks = None
                if a and a["marks"]:  # the professor's override replaces the verdict; the original is kept
                    marks = {k: {**m, "verdict": overrides[q["question_id"], k], "overridden": m["verdict"]}
                             if (q["question_id"], k) in overrides else m for k, m in a["marks"].items()}
                questions.append({**dict(q), "options": json.loads(q["options"]) if q["options"] else None,
                                  "answer": a and {k: v for k, v in a.items() if k not in ("web", "marks")},
                                  "web": a and a["web"], "marks": marks, "exposure": exposure(marks) if a else None,
                                  "gap": bool(a) and any(s["source"] == "none" or (s["grounding"] or {}).get("verdict")
                                                         == "unsupported" or (s["assumption"] or {}).get("state") == "rejected"
                                                         for s in a["steps"])})
        for q in questions:
            q["recommendation"] = recommend(q) if q["answer"] or q["type"] == "code" else None
        return {"course_code": code, "run": run_status(path) if path else None,
                "prerequisite": cfg.get("prerequisite_course"), "questions": questions}

    @app.get("/courses/{code}/assumptions")
    def list_assumptions(code: str):
        with conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM assumed_knowledge WHERE course_code = ? ORDER BY id", (code,))]

    @app.post("/courses/{code}/assumptions")
    def decide(code: str, body: DecisionBody):
        """Accept or reject a claim for the course; the same claim decided again updates its decision."""
        with conn() as c, c:
            if not c.execute("SELECT 1 FROM courses WHERE code = ?", (code,)).fetchone():
                raise HTTPException(404, "course not found")
            row = c.execute("SELECT id FROM assumed_knowledge WHERE course_code = ? AND claim = ?",
                            (code, body.claim)).fetchone()
            if row:
                c.execute("UPDATE assumed_knowledge SET decision = ?, decided_at = ? WHERE id = ?",
                          (body.decision, now(), row["id"]))
                return {"id": row["id"]}
            cur = c.execute("INSERT INTO assumed_knowledge (course_code, claim, decision, decided_at) VALUES (?, ?, ?, ?)",
                            (code, body.claim, body.decision, now()))
            return {"id": cur.lastrowid}

    @app.put("/runs/{run_id}/overrides/{qid}/{agent}")
    def override(run_id: str, qid: str, agent: str, body: OverrideBody):
        """The professor's verdict for one answer of one run; exposure is recomputed from it."""
        path = find_log(runs_dir, safe_id(run_id))
        a = path and next((r for r in read_log(path) if r["type"] == "answer" and r["question_id"] == qid), None)
        if not a:
            raise HTTPException(404, "no answer for that question in this run")
        if agent not in ("student", "web") or not a["marks"]:
            raise HTTPException(422, "only marked student or web answers can be overridden")
        with conn() as c, c:
            c.execute("INSERT OR REPLACE INTO verdict_overrides (run_id, question_id, agent, verdict) VALUES (?, ?, ?, ?)",
                      (run_id, qid, agent, body.verdict))
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

    @app.get("/versions/{vid}")
    def get_version(vid: str):
        with conn() as c:
            return dict(version_row(c, vid))

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


def assumption(step: dict, decisions: dict[int, dict]) -> dict | None:
    """Review state of an assumed_knowledge step: accepted (cites a valid accepted_id, skipped in review), decided
    since the run (same claim), or unreviewed. An unknown or rejected accepted_id counts as unreviewed."""
    if step["source"] != "assumed_knowledge":
        return None
    d = decisions.get(step["accepted_id"])
    if d and d["decision"] == "accepted":
        return {"state": "accepted", "id": d["id"]}
    d = next((d for d in decisions.values() if d["claim"] == step["claim"]), None)
    return {"state": d["decision"], "id": d["id"]} if d else {"state": "unreviewed"}


def from_env() -> FastAPI:
    """NOODLES_DATA / NOODLES_RUNS dirs; NOODLES_FAKE=1 swaps in fake model clients (no model calls)."""
    fake = os.environ.get("NOODLES_FAKE") == "1"
    if fake:
        from noodles.fakes import FakeOllama, FakeOpenAI
    return create_app(Path(os.environ.get("NOODLES_DATA", "data")), Path(os.environ.get("NOODLES_RUNS", "runs")),
                      ollama=FakeOllama() if fake else None, openai=FakeOpenAI() if fake else None)
