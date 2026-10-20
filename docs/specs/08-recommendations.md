# 08 Recommendations and summary

**Goal:** every question gets a recommendation, the review groups questions by it, and the summary page gives the verdict, key figures, top actions and the exposure grid.

**sys-design:** Lookup or reasoning, Recommendation rules, Stage 4 sections 1–2.

## Flow

1. Lookup or reasoning from the student's knowledge-step count.
2. Rules applied in order, first match wins. Rule 5 adds the "add a check" alternative. A recommendation that matches `current_format` reads "keep as is". Code questions: "not assessed (code question)".
3. Review list grouped by recommendation; summary page as on the canvas.

All in code, no LLM calls.

## Front end

`c1-summary`, `c2b-review-exposed` (recommendation block), review grouping in `c2-review`.

## Acceptance tests

One test per rule row, plus:

- A question with a gap gets "fix coverage first" whatever its exposure.
- A gap-free question without an answer key gets "not assessed".
- AI-exposed with 1 knowledge step → closed-book invigilated; with 2 → open-book invigilated or redesign, both with the add-a-check line.
- Student right, web wrong → keep open or take-home.
- A recommendation equal to `current_format` reads "keep as is".
- Summary counts match the per-question results.
