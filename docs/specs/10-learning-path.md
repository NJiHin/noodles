# 10 Learning path

**Goal:** the professor sees each topic's depth by week, which questions use it, and three findings: coverage gaps, only mentioned but assessed, taught but never assessed.

**sys-design:** Stage 4 section 3, Derived fields.

## Flow

All in code from the reviewed map and the run's citations:

1. Question → topics: each cited passage maps to the topics listing it as evidence.
2. Only mentioned but assessed: a topic a question uses whose deepest depth up to that question's `week_cutoff` is `mentioned`. Shows the week and page, linked to the PDF.
3. Taught but never assessed: topics no question uses.
4. Depth grid: topics by week, shaded by depth, with assessment weeks marked.
5. The citation limitation from sys-design is stated on the page.

## Front end

`c3-learning-path`.

## Acceptance tests

- A question citing a passage tagged with two topics counts for both.
- A topic used only in an `assumed_knowledge` or `none` step isn't counted as assessed.
- Depth "worked example" in week 7 doesn't count for a question with cutoff 6; only "mentioned" in week 5 is flagged.
- A topic no question cites is listed as never assessed.
