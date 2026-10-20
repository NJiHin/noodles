"""Stage 0: uploaded files -> stored PDFs -> one passage per page."""
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import opendataloader_pdf
import pypdfium2

ACCEPTED = {".pdf", ".pptx", ".docx"}
LEGACY = {".ppt", ".doc"}
PAGE_MARK = "<<<NOODLES PAGE %page-number%>>>"


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


def parse_pdfs(pdfs: list[Path]) -> dict[Path, list[str]]:
    """OpenDataLoader (fast mode) text per page, in reading order. Every page gets an entry."""
    out: dict[Path, list[str]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        opendataloader_pdf.convert([str(p) for p in pdfs], output_dir=tmp, format="text",
                                   image_output="off", quiet=True, include_header_footer=True,
                                   text_page_separator=PAGE_MARK)
        for pdf in pdfs:
            n = len(pypdfium2.PdfDocument(pdf))
            pages = [""] * n
            txt = Path(tmp) / f"{pdf.stem}.txt"
            raw = txt.read_text() if txt.exists() else ""
            for m in re.finditer(r"<<<NOODLES PAGE (\d+)>>>\n?(.*?)(?=<<<NOODLES PAGE \d+>>>|\Z)", raw, re.S):
                i = int(m.group(1))
                if 1 <= i <= n:
                    pages[i - 1] = m.group(2).strip()
            out[pdf] = pages
    return out


def ingest(conn: sqlite3.Connection, files_dir: Path, code: str, staged: list[Path], weeks: dict[str, int]) -> str:
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
        pages = parse_pdfs(pdfs)

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
                        "VALUES (?, ?, ?, ?, ?, ?, 'parser')",
                        [(vid, f"{code}-w{week}-{slug}-p{i}", slug, week, i, text)
                         for i, text in enumerate(pages[pdf], 1)])
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
