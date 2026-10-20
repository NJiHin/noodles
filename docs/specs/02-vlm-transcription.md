# 02 Page transcription (VLM)

**Goal:** pages with images, tables, equations or drawn diagrams get readable text, and the professor can see which pages were transcribed.

**sys-design:** Stage 0, Parsing pipeline steps 4–5 and the notes under it.

## Flow

1. After parsing (slice 01), flag a page if any of the four Stage 0 rules hold.
2. Each flagged page is rendered with pypdfium2 and sent to `qwen3-vl:2b` via Ollama. Its markdown replaces the page's passage text, with `origin = vlm`.
3. The materials page marks `vlm` passages.

Thresholds for "very little text" and "mostly garbled" are constants, set on the demo courses.

## Acceptance tests

Ollama is faked.

- A page with an image is flagged; a text-only page is not.
- A page under the text threshold is flagged.
- A page of mostly garbled characters is flagged.
- A page with vector drawings is flagged.
- A flagged page's passage text is the VLM output, `origin = vlm`; unflagged pages keep the parser text.
- If Ollama is unreachable, ingestion fails with a clear error and writes no passages for that version.

## Pilot (user runs)

One slide deck and one Word document from each demo course. Check flagged pages by eye and set the thresholds.
