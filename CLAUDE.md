# Noodles

IS4401 (NUS) group project. Simulated students limited to a course's materials take its assessments, alongside a web-search agent. The output is a course report centred on a review of the assessments.

- **`docs/sys-design.md` is the single source of truth.** Read it before any design or implementation work. If something here conflicts with it, `docs/sys-design.md` wins.
- `docs/brain_dump.md` is background, the literature review and the history of decisions. Parts of it are out of date, so don't treat it as current design.

## Tooling

- Python backend managed with `uv`. Use `uv add` and `uv run`.
- Front end: React (see `docs/sys-design.md`).

## Data rules

- Use only NUS course materials the professors have approved. Never scrape Canvas.
- Never commit course materials or run logs to the repo.
- No hosted tracing or telemetry services on course materials.
- $40 of OpenAI credits for the group. Pilot on small samples, and rely on the run-log cache to avoid repeat calls.
