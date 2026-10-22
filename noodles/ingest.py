"""Stage 0: uploaded files -> stored PDFs -> one passage per page."""
import hashlib
import io
import json
import re
import shutil
import string
import sqlite3
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import opendataloader_pdf
import pypdfium2
import pypdfium2.raw as pdfium_c

ACCEPTED = {".pdf", ".pptx", ".docx"}
LEGACY = {".ppt", ".doc"}
PAGE_MARK = "<<<NOODLES PAGE %page-number%>>>"

# Flagging thresholds (sys-design Stage 0, step 4). shortcut: guesses, set them on the demo courses (slice 02 pilot).
MIN_TEXT = 40          # characters; fewer is "very little text"
GARBLED_RATIO = 0.3    # share of non-space characters outside letters, digits and common punctuation
MIN_PATHS = 20         # vector path objects; this many or more is a drawing
PLAIN = set(string.ascii_letters + string.digits + string.punctuation + "–—‘’“”•…·°×")


class IngestError(Exception):
    pass


class FingerprintTaken(IngestError):
    """Adding the files would give the version the same materials as another version of the course."""
    def __init__(self, other: str):
        super().__init__(f"the course already has a version with exactly these files: {other}")
        self.other = other


def check_upload_name(name: str) -> None:
    ext = Path(name).suffix.lower()
    if ext in LEGACY:
        raise IngestError(f"{name}: legacy {ext} files aren't supported. Please re-save it as {ext}x and upload again.")
    if ext not in ACCEPTED:
        raise IngestError(f"{name}: only .pdf, .pptx and .docx files are accepted.")


def guess_week(name: str) -> int | None:
    """Week from a filename: 'Week05_Recursion' -> 5, 'L3-loops' -> 3, no number -> None."""
    stem = Path(name).stem.lower()
    m = re.search(r"(?:week|wk|w|lecture|lec|l|tutorial|tut|t|lab)[\s_-]*0*(\d{1,2})(?!\d)", stem)
    if not m:
        m = re.search(r"(?<!\d)0*(\d{1,2})(?!\d)", stem)
    return int(m.group(1)) if m else None


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", Path(name).stem.lower()).strip("-") or "file"


def unique_slugs(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for name in names:
        base = slug = slugify(name)
        i = 2
        while slug in seen:
            slug, i = f"{base}-{i}", i + 1
        seen.add(slug)
        out.append(slug)
    return out


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(code: str, files: list[tuple[str, str, int]]) -> str:
    """Fingerprint of the course code and each file (name, sha256 of its bytes, confirmed week)."""
    return hashlib.sha256(json.dumps([code, sorted(files)]).encode()).hexdigest()[:16]


def soffice() -> str:
    exe = shutil.which("soffice") or "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if not Path(exe).exists():
        raise IngestError("LibreOffice (soffice) is not installed; it is needed to convert Office files.")
    return exe


def to_pdf(src: Path, dest: Path) -> None:
    """Copy a PDF, or convert an Office file to PDF with headless LibreOffice."""
    if src.suffix.lower() == ".pdf":
        shutil.copyfile(src, dest)
        return
    with tempfile.TemporaryDirectory() as tmp:
        # own profile dir so parallel conversions don't fight over one LibreOffice profile
        cmd = [soffice(), f"-env:UserInstallation=file://{tmp}/profile", "--headless",
               "--convert-to", "pdf", "--outdir", tmp, str(src)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        out = Path(tmp) / f"{src.stem}.pdf"
        if r.returncode or not out.exists():
            raise IngestError(f"{src.name}: conversion to PDF failed. {r.stderr.strip()}")
        shutil.move(out, dest)


def _element_types(elements: list, types: dict[int, set[str]]) -> None:
    for e in elements:
        if "page number" in e:
            types.setdefault(e["page number"], set()).add(e.get("type", ""))
        for key in ("kids", "list items", "rows", "cells"):
            _element_types(e.get(key, []), types)


def parse_pdfs(pdfs: list[Path]) -> dict[Path, list[dict]]:
    """Per page: OpenDataLoader (fast mode) text in reading order, its element types, and the
    pypdfium2 vector path count. Every page gets an entry."""
    out: dict[Path, list[dict]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        opendataloader_pdf.convert([str(p) for p in pdfs], output_dir=tmp, format="text,json",
                                   image_output="off", quiet=True, include_header_footer=True,
                                   replace_invalid_chars="\ufffd", text_page_separator=PAGE_MARK)
        for pdf in pdfs:
            doc = pypdfium2.PdfDocument(pdf)
            pages = [{"text": "", "types": set(),
                      "paths": sum(1 for o in pg.get_objects() if o.type == pdfium_c.FPDF_PAGEOBJ_PATH)}
                     for pg in doc]
            txt, js = Path(tmp) / f"{pdf.stem}.txt", Path(tmp) / f"{pdf.stem}.json"
            raw = txt.read_text() if txt.exists() else ""
            for m in re.finditer(r"<<<NOODLES PAGE (\d+)>>>\n?(.*?)(?=<<<NOODLES PAGE \d+>>>|\Z)", raw, re.S):
                i = int(m.group(1))
                if 1 <= i <= len(pages):
                    pages[i - 1]["text"] = m.group(2).strip()
            types: dict[int, set[str]] = {}
            if js.exists():
                _element_types(json.loads(js.read_text()).get("kids", []), types)
            for i, t in types.items():
                if 1 <= i <= len(pages):
                    pages[i - 1]["types"] = t
            out[pdf] = pages
    return out


def flag_reasons(page: dict) -> list[str]:
    """Why a parsed page needs VLM transcription (sys-design Stage 0, step 4). Empty = keep parser text."""
    text = page["text"]
    chars = [ch for ch in text if not ch.isspace()]
    reasons = []
    if page["types"] & {"image", "table"}:
        reasons.append("image or table")
    if len(chars) < MIN_TEXT:
        reasons.append("little text")
    elif sum(ch not in PLAIN for ch in chars) / len(chars) > GARBLED_RATIO:
        reasons.append("garbled text")
    if page["paths"] >= MIN_PATHS:
        reasons.append("vector drawing")
    return reasons


def page_png(doc: pypdfium2.PdfDocument, i: int) -> bytes:
    """Page i (0-based) as the PNG the VLM sees; also served to the UI so reviewers see the same image."""
    buf = io.BytesIO()
    doc[i].render(scale=2).to_pil().save(buf, "PNG")
    return buf.getvalue()


def transcribe_flagged(pdf: Path, pages: list[dict], vlm, on_page=lambda: None) -> list[tuple[str, str]]:
    """(text, origin) per page: VLM markdown for flagged pages, parser text for the rest or when the VLM gives none."""
    doc = pypdfium2.PdfDocument(pdf)
    out = []
    for i, p in enumerate(pages):
        if not flag_reasons(p):
            out.append((p["text"], "parser"))
            continue
        text = vlm.transcribe(page_png(doc, i))
        on_page()
        out.append((text, "vlm") if text else (p["text"], "parser"))
    return out


def read_files(staged: list[Path], pdfs: list[Path], vlm, progress) -> list[list[tuple[str, str]]]:
    """Convert each file to its PDF, parse, transcribe flagged pages: (text, origin) per page, per file.
    progress({filename: {"done", "total"}}) is called as each file's flagged pages are transcribed."""
    for src, pdf in zip(staged, pdfs):
        to_pdf(src, pdf)
    parsed = parse_pdfs(pdfs)
    total = {src.name: sum(bool(flag_reasons(p)) for p in parsed[pdf]) for src, pdf in zip(staged, pdfs)}
    done = dict.fromkeys(total, 0)

    def report():
        progress({n: {"done": done[n], "total": total[n]} for n in total})

    def page_done(name):
        done[name] += 1
        report()
    report()
    return [transcribe_flagged(pdf, parsed[pdf], vlm, lambda n=src.name: page_done(n)) for src, pdf in zip(staged, pdfs)]


def passage_rows(vid: str, code: str, slug: str, week: int, pages: list[tuple[str, str]]) -> list[tuple]:
    return [(vid, f"{code}-w{week}-{slug}-p{i}", slug, week, i, text, origin) for i, (text, origin) in enumerate(pages, 1)]


INSERT_PASSAGE = "INSERT INTO passages (version_id, passage_id, file_slug, week, page, text, origin) VALUES (?, ?, ?, ?, ?, ?, ?)"


def ingest(conn: sqlite3.Connection, files_dir: Path, code: str, staged: list[Path], weeks: dict[str, int], vlm,
           progress) -> str:
    """Store, parse and write a version. Returns the existing version with the same materials if there is one.
    progress({filename: {"done", "total"}}) is called as each file's flagged pages are transcribed."""
    shas = {p.name: sha256(p.read_bytes()) for p in staged}
    fp = fingerprint(code, [(p.name, shas[p.name], weeks[p.name]) for p in staged])
    if row := conn.execute("SELECT id FROM versions WHERE fingerprint = ?", (fp,)).fetchone():
        return row["id"]
    # the ID is the fingerprint, unless a version that has since had files added still holds it
    vid = uuid.uuid4().hex[:16] if conn.execute("SELECT 1 FROM versions WHERE id = ?", (fp,)).fetchone() else fp

    dest = files_dir / vid
    work = Path(tempfile.mkdtemp(dir=files_dir.parent))
    try:
        slugs = unique_slugs([p.name for p in staged])
        pages = read_files(staged, [work / f"{s}.pdf" for s in slugs], vlm, progress)
        try:
            with conn:  # PDFs move inside the transaction, so DB rows and stored files land together
                conn.execute("INSERT OR IGNORE INTO courses (code) VALUES (?)", (code,))
                conn.execute("INSERT INTO versions (id, course_code, created_at, fingerprint) VALUES (?, ?, ?, ?)",
                             (vid, code, datetime.now(timezone.utc).isoformat(), fp))
                for src, slug, file_pages in zip(staged, slugs, pages):
                    week = weeks[src.name]
                    conn.execute("INSERT INTO files (version_id, slug, filename, week, sha256) VALUES (?, ?, ?, ?, ?)",
                                 (vid, slug, src.name, week, shas[src.name]))
                    conn.executemany(INSERT_PASSAGE, passage_rows(vid, code, slug, week, file_pages))
                conn.execute("INSERT INTO passages_fts(passages_fts) VALUES('rebuild')")
                shutil.rmtree(dest, ignore_errors=True)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(work, dest)
        except sqlite3.IntegrityError:
            # a concurrent confirm of the same files committed first: reuse it
            if row := conn.execute("SELECT id FROM versions WHERE fingerprint = ?", (fp,)).fetchone():
                return row["id"]
            raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return vid


def add_files(conn: sqlite3.Connection, files_dir: Path, vid: str, staged: list[Path], weeks: dict[str, int], vlm,
              progress) -> None:
    """Add files to a version in place; a file with the same name as one in the version replaces it.
    Other files, corrections, the map and assessments stay; map evidence on pages that no longer exist is dropped.
    Raises FingerprintTaken if the result would match another version of the course."""
    code = conn.execute("SELECT course_code FROM versions WHERE id = ?", (vid,)).fetchone()["course_code"]
    existing = {r["filename"]: dict(r) for r in conn.execute("SELECT * FROM files WHERE version_id = ?", (vid,))}
    taken = {f["slug"] for f in existing.values()}
    slugs = []
    for p in staged:  # a replaced file keeps its slug; a new one gets a slug not used in the version
        slug = existing[p.name]["slug"] if p.name in existing else unique_slugs([*taken, p.name])[-1]
        taken.add(slug)
        slugs.append(slug)
    shas = {p.name: sha256(p.read_bytes()) for p in staged}
    # shortcut: files stored before sha256 was recorded use their stored PDF's hash, which equals the upload's only for
    # PDF uploads; such a version just isn't found again by re-uploading its Office files
    kept = [(n, f["sha256"] or sha256((files_dir / vid / f"{f['slug']}.pdf").read_bytes()), f["week"])
            for n, f in existing.items() if n not in shas]
    fp = fingerprint(code, kept + [(p.name, shas[p.name], weeks[p.name]) for p in staged])
    if row := conn.execute("SELECT id FROM versions WHERE fingerprint = ? AND id != ?", (fp, vid)).fetchone():
        raise FingerprintTaken(row["id"])

    work = Path(tempfile.mkdtemp(dir=files_dir.parent))
    try:
        pdfs = [work / f"{s}.pdf" for s in slugs]
        pages = read_files(staged, pdfs, vlm, progress)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                for src, slug, pdf, file_pages in zip(staged, slugs, pdfs, pages):
                    rows = passage_rows(vid, code, slug, weeks[src.name], file_pages)
                    if src.name in existing:
                        keep = {r[1] for r in rows}
                        gone = [(vid, pid) for (pid,) in conn.execute(
                            "SELECT passage_id FROM passages WHERE version_id = ? AND file_slug = ?", (vid, slug)) if pid not in keep]
                        conn.executemany("DELETE FROM evidence WHERE version_id = ? AND passage_id = ?", gone)
                        conn.executemany("DELETE FROM passages WHERE version_id = ? AND passage_id = ?", gone)
                        conn.execute("UPDATE files SET week = ?, sha256 = ?, added_at = ? WHERE version_id = ? AND slug = ?",
                                     (weeks[src.name], shas[src.name], now, vid, slug))
                    else:
                        conn.execute("INSERT INTO files (version_id, slug, filename, week, sha256, added_at) VALUES (?, ?, ?, ?, ?, ?)",
                                     (vid, slug, src.name, weeks[src.name], shas[src.name], now))
                    # pages that stay keep their ID (map evidence still points at them) and take the new text
                    conn.executemany(INSERT_PASSAGE + " ON CONFLICT (version_id, passage_id) DO UPDATE SET "
                                     "text = excluded.text, origin = excluded.origin, page = excluded.page, heading = NULL", rows)
                conn.execute("UPDATE versions SET fingerprint = ?, materials_changed_at = ? WHERE id = ?", (fp, now, vid))
                conn.execute("INSERT INTO passages_fts(passages_fts) VALUES('rebuild')")
                for slug, pdf in zip(slugs, pdfs):
                    shutil.move(pdf, files_dir / vid / f"{slug}.pdf")
        except sqlite3.IntegrityError:  # another version took this fingerprint meanwhile
            if row := conn.execute("SELECT id FROM versions WHERE fingerprint = ? AND id != ?", (fp, vid)).fetchone():
                raise FingerprintTaken(row["id"])
            raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def read_document(src: Path, vlm, progress) -> str:
    """One file's text through the same pipeline (convert, parse, transcribe flagged pages), pages joined.
    progress({filename: {"done", "total"}}) as its flagged pages are transcribed."""
    with tempfile.TemporaryDirectory() as tmp:
        [pages] = read_files([src], [Path(tmp) / "doc.pdf"], vlm, progress)
    return "\n\n".join(text for text, _ in pages)
