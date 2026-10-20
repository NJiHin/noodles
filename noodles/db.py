"""Course store (SQLite). Tables as in sys-design "Course store"; each slice adds its own."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
  code TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS versions (
  id TEXT PRIMARY KEY,
  course_code TEXT NOT NULL REFERENCES courses(code),
  created_at TEXT NOT NULL,
  map_reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS files (
  version_id TEXT NOT NULL REFERENCES versions(id),
  slug TEXT NOT NULL,
  filename TEXT NOT NULL,
  week INTEGER NOT NULL,
  PRIMARY KEY (version_id, slug)
);
CREATE TABLE IF NOT EXISTS passages (
  version_id TEXT NOT NULL,
  passage_id TEXT NOT NULL,
  file_slug TEXT NOT NULL,
  week INTEGER NOT NULL,
  page INTEGER NOT NULL,
  text TEXT NOT NULL,
  origin TEXT NOT NULL CHECK (origin IN ('parser', 'vlm')),
  heading TEXT,
  UNIQUE (version_id, passage_id),
  FOREIGN KEY (version_id, file_slug) REFERENCES files(version_id, slug)
);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
  heading, text, content='passages'
);
CREATE TABLE IF NOT EXISTS concepts (
  version_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  name TEXT NOT NULL,
  aliases TEXT NOT NULL DEFAULT '[]',
  description TEXT,
  PRIMARY KEY (version_id, concept_id)
);
CREATE TABLE IF NOT EXISTS occurrences (
  version_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  week INTEGER NOT NULL,
  depth TEXT NOT NULL CHECK (depth IN ('mentioned', 'explained', 'worked_example', 'practised')),
  PRIMARY KEY (version_id, concept_id, week)
);
CREATE TABLE IF NOT EXISTS evidence (
  version_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  passage_id TEXT NOT NULL,
  PRIMARY KEY (version_id, concept_id, passage_id),
  FOREIGN KEY (version_id, passage_id) REFERENCES passages(version_id, passage_id)
);
CREATE INDEX IF NOT EXISTS evidence_by_passage ON evidence (version_id, passage_id);
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA)
