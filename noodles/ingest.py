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


def version_id(code: str, files: list[tuple[str, bytes, int]]) -> str:
    """Fingerprint of the course code, each file (name and bytes) and its confirmed week."""
    items = sorted((name, hashlib.sha256(data).hexdigest(), week) for name, data, week in files)
    return hashlib.sha256(json.dumps([code, items]).encode()).hexdigest()[:16]


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


def transcribe_flagged(pdf: Path, pages: list[dict], vlm) -> list[tuple[str, str]]:
    """(text, origin) per page: VLM markdown for flagged pages, parser text for the rest."""
    doc = pypdfium2.PdfDocument(pdf)
    out = []
    for i, p in enumerate(pages):
        if not flag_reasons(p):
            out.append((p["text"], "parser"))
            continue
        buf = io.BytesIO()
        doc[i].render(scale=2).to_pil().save(buf, "PNG")
        out.append((vlm.transcribe(buf.getvalue()), "vlm"))
    return out


def ingest(conn: sqlite3.Connection, files_dir: Path, code: str, staged: list[Path], weeks: dict[str, int], vlm) -> str:
    """Store, parse and write a version. Reuses an existing version with the same ID."""
    files = [(p.name, p.read_bytes(), weeks[p.name]) for p in staged]
    vid = version_id(code, files)
    if conn.execute("SELECT 1 FROM versions WHERE id = ?", (vid,)).fetchone():
        return vid

    dest = files_dir / vid
    work = Path(tempfile.mkdtemp(dir=files_dir.parent))
    try:
        slugs = unique_slugs([p.name for p in staged])
        pdfs = [work / f"{s}.pdf" for s in slugs]
        for src, pdf in zip(staged, pdfs):
            to_pdf(src, pdf)
        parsed = parse_pdfs(pdfs)
        pages = {pdf: transcribe_flagged(pdf, parsed[pdf], vlm) for pdf in pdfs}

        try:
            with conn:  # PDFs move inside the transaction, so DB rows and stored files land together
                conn.execute("INSERT OR IGNORE INTO courses (code) VALUES (?)", (code,))
                conn.execute("INSERT INTO versions (id, course_code, created_at) VALUES (?, ?, ?)",
                             (vid, code, datetime.now(timezone.utc).isoformat()))
                for src, slug, pdf in zip(staged, slugs, pdfs):
                    week = weeks[src.name]
                    conn.execute("INSERT INTO files (version_id, slug, filename, week) VALUES (?, ?, ?, ?)",
                                 (vid, slug, src.name, week))
                    conn.executemany(
                        "INSERT INTO passages (version_id, passage_id, file_slug, week, page, text, origin) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [(vid, f"{code}-w{week}-{slug}-p{i}", slug, week, i, text, origin)
                         for i, (text, origin) in enumerate(pages[pdf], 1)])
                conn.execute("INSERT INTO passages_fts(passages_fts) VALUES('rebuild')")
                shutil.rmtree(dest, ignore_errors=True)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(work, dest)
        except sqlite3.IntegrityError:
            # a concurrent confirm of the same files committed first: reuse it
            if conn.execute("SELECT 1 FROM versions WHERE id = ?", (vid,)).fetchone():
                return vid
            raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return vid


def read_document(src: Path, vlm) -> str:
    """One file's text through the same pipeline (convert, parse, transcribe flagged pages), pages joined."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "doc.pdf"
        to_pdf(src, pdf)
        pages = transcribe_flagged(pdf, parse_pdfs([pdf])[pdf], vlm)
    return "\n\n".join(text for text, _ in pages)
