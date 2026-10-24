# Slice specs

Vertical slices for building the system in `docs/sys-design.md`. That file is the source of truth for behaviour. These specs only set what each slice covers, its interfaces and its acceptance tests, and they refer to sys-design sections rather than repeating them.

Build in order. Each slice ends with something you can use in the browser.

| # | Slice | Screens (canvas board) |
|---|---|---|
| 01 | [Ingest and browse materials](01-ingest-materials.md) | upload, week confirm, materials (not mocked) |
| 02 | [Page transcription (VLM)](02-vlm-transcription.md) | materials, `vlm` marker (not mocked) |
| 03 | [Course map](03-course-map.md) | map review, job progress (not mocked) |
| 04 | [Assessments and questions](04-assessments.md) | assessment upload, question confirm (not mocked) |
| 05 | [Student attempt](05-student-attempt.md) | review: question and steps (`c2-review`) |
| 06 | [Grounding checker](06-grounding.md) | review: citation verdicts (`c2-review`) |
| 07 | [Web agent and marker](07-web-and-marker.md) | review: both answers, override (`c2-review`, `c2b`) |
| 08 | [Recommendations and summary](08-recommendations.md) | summary (`c1-summary`), review grouping (`c2b`) |
| 09 | [Assumed-knowledge decisions](09-assumed-knowledge.md) | review: accept or reject (`c2c-review-assumption`) |
| 10 | [Learning path](10-learning-path.md) | learning path (`c3-learning-path`) |
| 11 | [Versions and changes](11-versions-and-changes.md) | changes (`c5-changes`), map review ID diff |
| 12 | [Method, limitations and cost](12-method-and-cost.md) | method (`c6-method`) |
| 13 | [Evaluation](13-evaluation.md) | none (scripts only) |

Slice 02 can move later if the demo materials are mostly text. It must land before pilots on real courses.

## Conventions

- **Layout:** Python package `noodles/` at the repo root, run with `uv`. FastAPI app in `noodles/api.py`. React front end in `frontend/` (Vite). (Proposal.)
- **Front end:** screens are designed on the `/made` canvas (`canvas/`, local only) before their slice is built, then ported 1:1. Screens marked "not mocked" need a board first. Keep visuals uncluttered.
- **Source links:** every passage shown anywhere in the UI links to its source PDF at that page (sys-design Stage 0, step 7).
- **Tests (`/tdd`):** pytest through the public interface: HTTP endpoints via FastAPI's `TestClient`, and the pipeline's public functions. The OpenAI and Ollama clients are replaced by fakes, so tests make no paid calls. Fixtures are small synthetic PDFs and Office files built in the tests, never course materials.
- **Pilots:** each slice with LLM calls ends with a pilot on a small sample of a demo course. Claude prepares the command; the user runs it.
- **Schema:** each slice creates only its own tables, as written in sys-design "Course store". `PRAGMA foreign_keys = ON` on every connection.

## Not in these slices

Code questions and everything under sys-design "Roadmap".
