# 01 Ingest and browse materials

**Goal:** the professor creates a course, uploads its weekly files, confirms the week of each, and browses the result: every file and page, with a link that opens the source PDF at that page.

**sys-design:** Stage 0 (Parsing pipeline steps 1–3, 6–7), Course store (`courses`, `versions`, `files`, `passages`), Course-level versioning.

## Flow

1. Professor enters a course code and uploads `.pdf`, `.pptx` and `.docx` files. `.ppt` and `.doc` are rejected with a request to re-save.
2. Backend guesses each file's week from its filename. The professor confirms or corrects each week.
3. On confirm: the version ID is the fingerprint of the files' bytes and their confirmed weeks. Office files go through LibreOffice to PDF. Each PDF is stored at `data/files/<version_id>/<slug>.pdf` and parsed with OpenDataLoader (fast mode). One passage per page, `origin = parser`.
4. Materials page: files grouped by week, each with its page count. Each page shows its text and opens `/files/<version_id>/<slug>.pdf#page=N`.

If a version with the same ID already exists, confirm reuses it and parses nothing.

## Backend

- `POST /courses/{code}/uploads`: files in, week guesses out.
- `POST /courses/{code}/versions`: confirmed weeks in, runs steps 3, returns the version ID.
- `GET /versions/{id}/files`: files and passages for the materials page.
- `GET /files/{version_id}/{slug}.pdf`: serves the stored PDF.

## Front end (not mocked)

Upload and week confirm, materials page.

## Acceptance tests

- `.ppt` or `.doc` upload is rejected with a re-save message; `.pdf`, `.pptx`, `.docx` are accepted.
- Week guess: `Week05_Recursion.pptx` → 5, `L3-loops.pdf` → 3, a name with no number → no guess (professor must pick).
- Two files whose names give the same slug in one version get distinct slugs.
- A 3-page PDF in week 5 gives passages `<course>-w5-<slug>-p1` to `-p3`, `origin = parser`.
- Same files and weeks give the same version ID. Changing one file's week gives a different ID.
- The stored PDF is served, and its page count matches the passage count.
- A `.docx` is converted to PDF before parsing.

## Out of scope

VLM transcription (02), assessments (04).
