"""Stage 1: weekly extractors -> orchestrator -> draft map; professor-reviewed map -> store, headings, FTS."""
import asyncio
import json
import re
import sqlite3
from datetime import datetime, timezone
from itertools import groupby
from typing import Literal

from pydantic import BaseModel

from noodles.llm import LUNA, SOL, Run

Depth = Literal["mentioned", "explained", "worked_example", "practised"]
EXTRACT_V, ORCH_V = "extract-v1", "orchestrate-v1"


class WeekConcept(BaseModel):
    name: str
    description: str
    depth: Depth
    evidence: list[str]


class WeekRecords(BaseModel):
    concepts: list[WeekConcept]


class Occurrence(BaseModel):
    week: int
    depth: Depth
    evidence: list[str]


class Concept(BaseModel):
    concept_id: str
    name: str
    aliases: list[str]
    description: str
    occurrences: list[Occurrence]


class MergedMap(BaseModel):
    concepts: list[Concept]


EXTRACT_PROMPT = """You extract the topics a university course teaches in one week, from that week's materials.
Each passage starts with its ID in brackets. Return one record per topic taught or used this week:
- name: the most precise standard term for the topic
- description: one line in your own words on how this week covers it
- depth, the deepest treatment this week: "mentioned" (named in passing), "explained" (defined or explained),
  "worked_example" (shown in a worked example), "practised" (students do exercises on it)
- evidence: the IDs of the passages that support it, copied exactly
Return a list of topic records, not a summary. Use only the passages given."""

ORCH_PROMPT = """You merge weekly topic records of one course into a course map, one record per topic.
- Merge records that are the same topic, across and within weeks.
- name: the most precise standard term (not the earliest); keep the other names as aliases.
- concept_id: "<course>:<short-lowercase-name>", e.g. "CS1010:recursion".
- description: one optional line on how the course covers the topic.
- occurrences: one per week the topic appears in, with that week's depth and evidence IDs copied exactly.
- previous_concepts are the course's topics from its previous reviewed version, a reference for merging only:
  reuse a concept_id when a topic is the same; add new concepts freely when a topic is new.
Do not invent topics, weeks or evidence."""


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def version_passages(conn: sqlite3.Connection, vid: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT p.*, f.filename FROM passages p JOIN files f ON f.version_id = p.version_id "
                        "AND f.slug = p.file_slug WHERE p.version_id = ? ORDER BY p.week, f.filename, p.page",
                        (vid,)).fetchall()


async def extract_week(run: Run, week: int, passages: list) -> WeekRecords:
    body = f"Week {week} passages:\n\n" + "\n\n".join(f"[{p['passage_id']}] {p['text']}" for p in passages)
    return await run.call("extractor", LUNA, EXTRACT_V,
                          [{"role": "system", "content": EXTRACT_PROMPT}, {"role": "user", "content": body}],
                          WeekRecords)


async def build_map(run: Run, conn: sqlite3.Connection, code: str, vid: str, previous: list[dict]) -> MergedMap:
    """Run the extractors (in parallel) and the orchestrator; write the draft to the run log.
    previous: the previous reviewed version's concepts (concept_id, name, aliases), or [] on a first version."""
    by_week = [(w, list(ps)) for w, ps in groupby(version_passages(conn, vid), key=lambda p: p["week"])]
    records = await asyncio.gather(*(extract_week(run, w, ps) for w, ps in by_week))
    weekly = {str(w): r.model_dump()["concepts"] for (w, _), r in zip(by_week, records)}
    body = json.dumps({"course": code, "previous_concepts": previous, "weeks": weekly}, indent=1)
    merged = await run.call("orchestrator", SOL, ORCH_V,
                            [{"role": "system", "content": ORCH_PROMPT}, {"role": "user", "content": body}], MergedMap)
    seen: set[str] = set()
    for c in merged.concepts:  # IDs must carry the course code and be unique
        if not c.concept_id.startswith(f"{code}:"):
            c.concept_id = f"{code}:{slug(c.concept_id.split(':')[-1] or c.name)}"
        base, i = c.concept_id, 2
        while c.concept_id in seen:
            c.concept_id, i = f"{base}-{i}", i + 1
        seen.add(c.concept_id)
    run.write({"type": "draft", "map": merged.model_dump()})
    return merged


class MapError(Exception):
    pass


def save_map(conn: sqlite3.Connection, vid: str, concepts: list[Concept]) -> None:
    """Write the reviewed map, rebuild headings and FTS, and mark the map reviewed."""
    code = conn.execute("SELECT course_code FROM versions WHERE id = ?", (vid,)).fetchone()["course_code"]
    ids = [c.concept_id for c in concepts]
    if len(set(ids)) != len(ids):
        raise MapError("two topics have the same concept ID")
    if bad := [i for i in ids if not i.startswith(f"{code}:")]:
        raise MapError(f"concept IDs must start with {code}: {', '.join(bad)}")
    known = {r[0]: r[1] for r in conn.execute("SELECT passage_id, week FROM passages WHERE version_id = ?", (vid,))}
    for c in concepts:
        weeks = [o.week for o in c.occurrences]
        if len(set(weeks)) != len(weeks):
            raise MapError(f"{c.concept_id} lists a week twice")
        if missing := sorted({e for o in c.occurrences for e in o.evidence} - known.keys()):
            raise MapError(f"{c.concept_id} cites passages that don't exist: {', '.join(missing)}")
        if wrong := sorted(e for o in c.occurrences for e in o.evidence if known[e] != o.week):
            raise MapError(f"{c.concept_id} lists evidence under the wrong week: {', '.join(wrong)}")
    with conn:
        for t in ("evidence", "occurrences", "concepts"):
            conn.execute(f"DELETE FROM {t} WHERE version_id = ?", (vid,))
        for c in concepts:
            conn.execute("INSERT INTO concepts (version_id, concept_id, name, aliases, description) VALUES (?, ?, ?, ?, ?)",
                         (vid, c.concept_id, c.name, json.dumps(c.aliases), c.description or None))
            for o in c.occurrences:
                conn.execute("INSERT INTO occurrences (version_id, concept_id, week, depth) VALUES (?, ?, ?, ?)",
                             (vid, c.concept_id, o.week, o.depth))
                conn.executemany("INSERT OR IGNORE INTO evidence (version_id, concept_id, passage_id) VALUES (?, ?, ?)",
                                 [(vid, c.concept_id, e) for e in o.evidence])
        rebuild_headings(conn, vid)
        conn.execute("UPDATE versions SET map_reviewed_at = ? WHERE id = ?", (datetime.now(timezone.utc).isoformat(), vid))


def topic_label(name: str, aliases: list[str]) -> str:
    return f"{name} (also: {', '.join(aliases)})" if aliases else name


def rebuild_headings(conn: sqlite3.Connection, vid: str) -> None:
    """Contextual heading per passage from the passage-to-topic index, then rebuild FTS."""
    code = conn.execute("SELECT course_code FROM versions WHERE id = ?", (vid,)).fetchone()["course_code"]
    topics: dict[str, list[str]] = {}
    for r in conn.execute("SELECT e.passage_id, c.name, c.aliases FROM evidence e JOIN concepts c "
                          "ON c.version_id = e.version_id AND c.concept_id = e.concept_id "
                          "WHERE e.version_id = ? ORDER BY c.name", (vid,)):
        topics.setdefault(r["passage_id"], []).append(topic_label(r["name"], json.loads(r["aliases"])))
    for p in version_passages(conn, vid):
        head = f"[{code} | Week {p['week']} | {p['filename']}"
        if t := topics.get(p["passage_id"]):
            head += f" | Topics: {'; '.join(t)}"
        conn.execute("UPDATE passages SET heading = ? WHERE version_id = ? AND passage_id = ?",
                     (head + "]", vid, p["passage_id"]))
    conn.execute("INSERT INTO passages_fts(passages_fts) VALUES('rebuild')")


def load_map(conn: sqlite3.Connection, vid: str) -> list[dict]:
    """The reviewed map in the merged-map format."""
    occ: dict[str, list[dict]] = {}
    for o in conn.execute("SELECT * FROM occurrences WHERE version_id = ? ORDER BY week", (vid,)):
        ev = [r[0] for r in conn.execute("SELECT e.passage_id FROM evidence e JOIN passages p ON p.version_id = "
                                         "e.version_id AND p.passage_id = e.passage_id WHERE e.version_id = ? AND "
                                         "e.concept_id = ? AND p.week = ? ORDER BY p.passage_id",
                                         (vid, o["concept_id"], o["week"]))]
        occ.setdefault(o["concept_id"], []).append({"week": o["week"], "depth": o["depth"], "evidence": ev})
    return [{"concept_id": c["concept_id"], "name": c["name"], "aliases": json.loads(c["aliases"]),
             "description": c["description"] or "", "occurrences": occ.get(c["concept_id"], [])}
            for c in conn.execute("SELECT * FROM concepts WHERE version_id = ? ORDER BY name", (vid,))]
