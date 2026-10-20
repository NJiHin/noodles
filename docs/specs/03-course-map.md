# 03 Course map

**Goal:** the professor runs extraction on a version, watches it progress, then reviews and corrects the map. Confirming it builds everything retrieval needs.

**sys-design:** Stage 1, Run log, Course store (`concepts`, `occurrences`, `evidence`, `passages_fts`), Implementation (models).

This slice also builds two pieces every later slice reuses:

- **LLM call wrapper:** fingerprints a call's inputs (content it sees, prompt version, model), returns a cached result from any run log under the course code, or calls OpenAI with structured outputs, retries, a concurrency limit, and appends the record (with token usage) to the run's JSONL as soon as it finishes.
- **Background job:** a run starts as an asyncio task in the backend process. `GET /runs/{run_id}` reports its stage and progress, read from the run log. The UI polls it. (Proposal.)

## Flow

1. `POST /versions/{id}/map-runs` starts a run: one `gpt-6-luna` extractor call per week (in parallel), then one `gpt-6-sol` orchestrator call. The draft map stays in the run log.
2. Map review screen: each topic with aliases, description, and per-week depth and evidence. Evidence links open the PDF at that page.
3. Edits (proposal): rename, edit aliases, change a week's depth, remove an evidence passage, merge two topics, delete a topic.
4. Confirm writes `concepts`, `occurrences` and `evidence`, builds each passage's contextual heading, rebuilds `passages_fts`, and sets `map_reviewed_at`.

## Front end (not mocked)

Run progress, map review.

## Acceptance tests

OpenAI is faked.

- Each extractor call sees only its own week's passages.
- A second run with identical inputs makes no API calls and returns the same map.
- Changing one week's passages reruns only that week's extractor call (plus the orchestrator).
- A run interrupted after some calls resumes without repeating them.
- Every run-log record has a fingerprint, call type, token usage and output.
- An extractor or orchestrator output that fails its schema is retried, then fails the run with an error.
- Confirm writes the reviewed map. Evidence pointing at a passage that doesn't exist is rejected.
- Headings follow the sys-design format. A passage no topic claims gets a heading without topics.
- After confirm, an FTS search for a topic's alias finds the passages tagged with it.
- Merge, rename and delete edits are reflected in the stored map.

## Pilot (user runs)

Three weeks of one demo course. Check the map by eye and the run's cost.
