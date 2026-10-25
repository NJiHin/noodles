"""Evaluation beside the app (docs/specs/13-evaluation.md): export each question's trace input, merge the traces into
the frozen reference set, score the version's results against it. Files under data/eval/, never committed.
Run: uv run python -m noodles.eval export|merge|score <version_id>"""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from noodles import db
from noodles.llm import fingerprint
from noodles.student import reachable, student_conn
from noodles.web import question_text

TRACES = 3  # independent traces per question (spec: raise it if traces disagree often)
NIM = "not in materials"
TRACE_PROMPT = f"""You are the required knowledge finder for one exam question. You are given the question, its answer key and every
course passage a student could have read by the question's week. Do not solve the question: work back from the known answer to the
knowledge needed to reach it from the question. List those steps: the subject knowledge each step needs, and the IDs of the passages
that teach it.
- Secondary-school and pre-university (A-level/JC) knowledge (arithmetic, algebra, reading a table, substituting values into a
  formula you are given) and anything printed in the question itself (its data, tables, given formulas) need no passage. List
  at least one step: when the answer rests only on these, one step with an empty list [] and the reason "general knowledge".
- Exception: when the question says something was taught in class (e.g. "the normal equations discussed in class") and this
  question's answer uses it, knowing it is a step even if the question prints it, and "in class" means the passages up to this
  week. A sub-question that doesn't use it (e.g. one that only asks for a sum from the table) gets no such step.
- If no passage teaches a step, write "{NIM}" instead of passage IDs. Never stretch a citation: a passing mention that doesn't
  teach the step doesn't support it.
- Knowledge beyond pre-university level that the course's stated entry requirements imply but no passage teaches: an empty list
  [] and a one-line "reason" naming the entry requirement. When unsure between this and "{NIM}", choose "{NIM}".
Write only JSON: {{"model": "<your model>", "steps": [{{"knowledge": "...", "passages": ["<passage_id>", ...] or "{NIM}" or [],
"reason": "<only for assumed knowledge>"}}]}}"""


def _dir(data_dir: Path, conn, vid: str) -> Path:
    code = conn.execute("SELECT course_code FROM versions WHERE id = ?", (vid,)).fetchone()
    if not code:
        raise ValueError(f"no version {vid}")
    return Path(data_dir) / "eval" / code[0] / vid


def _prereq(conn, course: str | None) -> str | None:
    """The prerequisite course's latest reviewed version, as a test-drive picks it."""
    if not course:
        return None
    p = conn.execute("SELECT id FROM versions WHERE course_code = ? AND map_reviewed_at IS NOT NULL "
                     "ORDER BY created_at DESC LIMIT 1", (course,)).fetchone()
    if not p:
        raise ValueError(f"{course} has no version with a reviewed map")
    return p[0]


def _questions(conn, vid: str) -> list[dict]:
    """Confirmed questions with marking material, code questions left out (spec: they get no entry)."""
    rows = conn.execute(
        "SELECT q.question_id, q.context, q.text, q.options, q.type, q.marking_material, a.assessment_id, a.week_cutoff "
        "FROM questions q JOIN assessments a ON a.version_id = q.version_id AND a.assessment_id = q.assessment_id "
        "WHERE q.version_id = ? AND q.type != 'code' AND q.marking_material IS NOT NULL ORDER BY a.week_cutoff, q.rowid", (vid,))
    return [{**dict(r), "options": json.loads(r["options"]) if r["options"] else None} for r in rows]


def _input(sconn, q: dict, vid: str, prereq: str | None) -> dict:
    """What a trace sees: the question as the agents see it, its key, and the passages the student can reach."""
    passages = [{"passage_id": i, "heading": h, "text": t} for i, h, t in
                reachable(sconn, vid, q["week_cutoff"], prereq)]
    out = {"question_id": q["question_id"], "assessment_id": q["assessment_id"], "week_cutoff": q["week_cutoff"],
           "prerequisite": prereq, "question": question_text(q), "marking_material": q["marking_material"], "passages": passages}
    return {**out, "fingerprint": fingerprint(out), "instructions": TRACE_PROMPT}  # the prompt is not in the fingerprint


def _reference(base: Path) -> dict:
    f = base / "reference.json"
    return json.loads(f.read_text()) if f.exists() else {}


def export(data_dir: Path, vid: str, prerequisite: str | None = None) -> list[str]:
    """Write inputs/<question_id>.json for each keyed question without a frozen entry. Returns their IDs."""
    path = Path(data_dir) / "noodles.db"
    conn, sconn = db.connect(path), student_conn(path)
    try:
        base, prereq = _dir(data_dir, conn, vid), _prereq(conn, prerequisite)
        done = _reference(base)
        (base / "inputs").mkdir(parents=True, exist_ok=True)
        out = []
        for q in _questions(conn, vid):
            if q["question_id"] in done:
                continue
            (base / "inputs" / f"{q['question_id']}.json").write_text(json.dumps(_input(sconn, q, vid, prereq), indent=1))
            out.append(q["question_id"])
        return out
    finally:
        conn.close(), sconn.close()


def _trace(f: Path) -> dict:
    """A trace file, checked for the fields merge relies on."""
    t = json.loads(f.read_text())
    if not isinstance(t.get("steps"), list) or not all(
            isinstance(x, dict) and "knowledge" in x and (x.get("passages") == NIM or isinstance(x.get("passages"), list))
            for x in t["steps"]):
        raise ValueError(f'{f.name}: each step needs "knowledge" and "passages" (a list of IDs, or "{NIM}")')
    return t


def merge(data_dir: Path, vid: str) -> list[str]:
    """Freeze an entry for each exported question with TRACES traces and no entry yet. Returns their IDs.
    Gap if any trace has a step not in the materials; reference passages are those cited by a majority of traces."""
    conn = db.connect(Path(data_dir) / "noodles.db")
    try:
        base = _dir(data_dir, conn, vid)
    finally:
        conn.close()
    ref, out = _reference(base), []
    for f in sorted((base / "inputs").glob("*.json")):
        qid = f.stem
        traces = [_trace(t) for t in sorted((base / "traces").glob(f"{qid}.*.json"))]
        if qid in ref or len(traces) < TRACES:
            continue
        cited = [{p for x in t["steps"] if x["passages"] != NIM for p in x["passages"]} for t in traces]
        inp = json.loads(f.read_text())
        ref[qid] = {**{k: inp[k] for k in ("question_id", "assessment_id", "week_cutoff", "prerequisite", "fingerprint")},
                    "coverage": "gap" if any(x["passages"] == NIM for t in traces for x in t["steps"]) else "covered",
                    "passages": sorted(p for p in set().union(*cited) if sum(p in c for c in cited) * 2 > len(traces)),
                    "traces": traces, "model": traces[0].get("model"), "frozen_at": datetime.now(timezone.utc).isoformat()}
        out.append(qid)
    (base / "reference.json").write_text(json.dumps(ref, indent=1))
    return out


def _review(data_dir: Path, runs_dir: Path, vid: str) -> dict:
    """Each question's result as the assessment review shows it: newest across runs, that run's overrides applied.
    shortcut: reads it through the app as the UI does; move get_review out of create_app if this is ever slow."""
    from fastapi.testclient import TestClient
    from noodles.api import create_app
    with TestClient(create_app(data_dir, runs_dir)) as c:
        r = c.get(f"/versions/{vid}/review")
        r.raise_for_status()
        return {q["question_id"]: q for q in r.json()["questions"]}


def _detail(entry: dict, q: dict, ref_gap: bool) -> str:
    """Why the two disagree: the reference's untaught steps, or the student's steps behind the system's gap."""
    if ref_gap:
        steps = {}
        for n, t in enumerate(entry["traces"], 1):
            for x in t["steps"]:
                if x["passages"] == NIM:
                    steps.setdefault(x["knowledge"], []).append(str(n))
        return "; ".join(f"{NIM}: {k} (trace {', '.join(ns)})" for k, ns in steps.items())
    return "; ".join(f"student: {x['claim']}" for x in q["answer"]["steps"]
                     if x["source"] == "none" or (x.get("grounding") or {}).get("verdict") == "unsupported")


def _totals(rows: list[dict]) -> dict:
    done = [r for r in rows if r["system"] != "no result"]
    n, rec = len(done), [r["recall"] for r in done if r["recall"] is not None]
    rate = lambda k: sum(r[k] for r in done) / n if n else "n/a"
    return {"questions": n, "agreement": rate("agree"), "correct": rate("correct"),
            "gaps_found": sum(r["reference"] == r["system"] == "gap" for r in done),
            "gaps_missed": sum(r["reference"] == "gap" != r["system"] for r in done),
            "false_gaps": sum(r["reference"] == "covered" and r["system"] == "gap" for r in done),
            "recall": sum(rec) / len(rec) if rec else "n/a"}


def _detection(rows: list[dict], key: str, planted) -> dict:
    hit = [r for r in rows if planted(r[f"expected_{key}"])]
    found = sum(planted(r[key]) for r in hit)
    return {"planted": len(hit), "detected": found, "detection_rate": found / len(hit) if hit else "n/a",
            "false_flags": sum(planted(r[key]) and not planted(r[f"expected_{key}"]) for r in rows)}


def _score_labels(data_dir: Path, runs_dir: Path, vid: str, labels: dict) -> dict:
    """Perturbed set: {question_id: {"gap": bool, "exposure": cell}} against the results after overrides."""
    review, rows = _review(data_dir, runs_dir, vid), []
    for qid, lab in labels.items():
        q = review.get(qid)
        if q and q["answer"]:
            rows.append({"question_id": qid, "expected_gap": lab["gap"], "gap": q["gap"],
                         "expected_exposure": lab["exposure"], "exposure": q["exposure"]})
    return {"rows": rows, "totals": {"coverage": _detection(rows, "gap", bool),
                                     "exposure": _detection(rows, "exposure", lambda e: e == "ai_exposed")}}


def score(data_dir: Path, runs_dir: Path, vid: str, labels: dict | None = None) -> dict:
    """Rows per frozen entry and totals (all, and per assessment); also written to scores.csv.
    With labels (the perturbed set), detection rate and false flags instead."""
    if labels is not None:
        return _score_labels(data_dir, runs_dir, vid, labels)
    path = Path(data_dir) / "noodles.db"
    conn, sconn = db.connect(path), student_conn(path)
    try:
        base = _dir(data_dir, conn, vid)
        ref, qs = _reference(base), {q["question_id"]: q for q in _questions(conn, vid)}
        for qid, e in ref.items():
            if qid not in qs or _input(sconn, qs[qid], vid, e["prerequisite"])["fingerprint"] != e["fingerprint"]:
                raise ValueError(f"{qid}: the question or its materials changed after its entry was frozen; trace it again")
    finally:
        conn.close(), sconn.close()
    review, rows = _review(data_dir, runs_dir, vid), []
    for qid, e in ref.items():
        q = review.get(qid)
        row = {"question_id": qid, "assessment_id": e["assessment_id"], "reference": e["coverage"]}
        if not q or not q["answer"]:
            rows.append({**row, "system": "no result", "agree": None, "correct": None, "recall": None, "detail": ""})
            continue
        cited = {p["passage_id"] for x in q["answer"]["steps"] for p in x.get("evidence") or []}
        system = "gap" if q["gap"] else "covered"
        rows.append({**row, "system": system, "agree": system == e["coverage"],
                     "correct": ((q["marks"] or {}).get("student") or {}).get("verdict") == "correct",
                     "recall": len(cited & set(e["passages"])) / len(e["passages"]) if e["passages"] else None,
                     "detail": "" if system == e["coverage"] else _detail(e, q, e["coverage"] == "gap")})
    totals = {"all": _totals(rows)} | {a: _totals([r for r in rows if r["assessment_id"] == a])
                                       for a in dict.fromkeys(r["assessment_id"] for r in rows)}
    with (base / "scores.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["question_id"])
        w.writeheader(), w.writerows(rows)
    return {"rows": rows, "totals": totals}


if __name__ == "__main__":
    import argparse
    import os
    ap = argparse.ArgumentParser(prog="python -m noodles.eval", description="Reference-set evaluation (docs/specs/13-evaluation.md)")
    ap.add_argument("step", choices=["export", "merge", "score"])
    ap.add_argument("version_id")
    ap.add_argument("--prerequisite", help="export: the prerequisite course code used by the test-drive")
    ap.add_argument("--labels", help="score: a perturbed-set labels.json in place of the reference set")
    a = ap.parse_args()
    data, runs = Path(os.environ.get("NOODLES_DATA", "data")), Path(os.environ.get("NOODLES_RUNS", "runs"))
    if a.step == "export":
        print("exported:", ", ".join(export(data, a.version_id, a.prerequisite)) or "nothing new")
    elif a.step == "merge":
        print("frozen:", ", ".join(merge(data, a.version_id)) or f"nothing (each question needs {TRACES} traces)")
    else:
        s = score(data, runs, a.version_id, json.loads(Path(a.labels).read_text()) if a.labels else None)
        for r in s["rows"]:
            print("  ".join(f"{v}" for k, v in r.items() if k != "detail"), r.get("detail") or "")
        for name, t in s["totals"].items():
            print(f"{name}: " + ", ".join(f"{k} {v:.2f}" if isinstance(v, float) else f"{k} {v}" for k, v in t.items()))
