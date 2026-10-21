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
  map_reviewed_at TEXT,
  fingerprint TEXT,
  materials_changed_at TEXT
);
CREATE TABLE IF NOT EXISTS files (
  version_id TEXT NOT NULL REFERENCES versions(id),
  slug TEXT NOT NULL,
  filename TEXT NOT NULL,
  week INTEGER NOT NULL,
  sha256 TEXT,
  added_at TEXT,
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
CREATE TABLE IF NOT EXISTS assessments (
  version_id TEXT NOT NULL,
  assessment_id TEXT NOT NULL,
  week_cutoff INTEGER NOT NULL,
  current_format TEXT NOT NULL CHECK (current_format IN ('take_home', 'online_quiz', 'invigilated_exam')),
  PRIMARY KEY (version_id, assessment_id)
);
CREATE TABLE IF NOT EXISTS assessment_files (
  version_id TEXT NOT NULL,
  assessment_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('paper', 'answers')),
  filename TEXT NOT NULL,
  text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
  version_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  assessment_id TEXT NOT NULL,
  text TEXT NOT NULL,
  options TEXT,
  type TEXT NOT NULL CHECK (type IN ('mcq', 'true_false', 'short', 'numeric', 'open', 'code')),
  marking_material TEXT,
  PRIMARY KEY (version_id, question_id)
);
CREATE TABLE IF NOT EXISTS assumed_knowledge (
  id INTEGER PRIMARY KEY,
  course_code TEXT NOT NULL REFERENCES courses(code),
  claim TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected')),
  decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verdict_overrides (
  run_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  agent TEXT NOT NULL CHECK (agent IN ('student', 'web')),
  verdict TEXT NOT NULL CHECK (verdict IN ('correct', 'partial', 'incorrect')),
  PRIMARY KEY (run_id, question_id, agent)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# columns added after a table was first created: databases made before them get them on start
ADDED = {"versions": ["fingerprint TEXT", "materials_changed_at TEXT"], "files": ["sha256 TEXT", "added_at TEXT"]}


def init(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        for table, cols in ADDED.items():
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            for col in cols:
                if col.split()[0] not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
        conn.execute("UPDATE versions SET fingerprint = id WHERE fingerprint IS NULL")  # the ID is the fingerprint at creation
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS versions_by_fingerprint ON versions (fingerprint)")
