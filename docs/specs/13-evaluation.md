# 13 Evaluation

**Goal:** numbers for the documentation's Evaluation section: how often the system's coverage verdicts, answers and citations agree with a frozen reference, and how many planted problems it catches.

**sys-design:** Evaluation (perturbed set, reference set, documentation examples), Stage 2 and 3 (step sources), Right and wrong.

Not part of the product: no screen, no sidebar entry, no API route. Professors never have a reference set, so it lives in scripts and files beside the app.

## Reference set (silver standard)

### Shape

- One reference set per course version, made of one entry per question. Each entry is traced against the materials up to its own assessment's `week_cutoff`, the same passages the student can reach.
- Built week by week: when a new week's quiz is confirmed, entries are added for its questions only. Existing entries are frozen and never rebuilt.
- Questions without marking material, and code questions, get no entry.

### Flow

1. **Export (code):** `uv run python -m noodles.eval export <version_id> [--prerequisite <course_code>]` writes one input file per question that has no entry yet. Pass the same prerequisite as the test-drive being scored, so the reference sees the same passages as the student:
   - the question as every agent sees it (context, text, options);
   - the marking material;
   - every passage within the week limit (ID, heading, text), from the same query the student's fingerprint uses (`reachable`);
   - a fingerprint of all of the above: `llm.fingerprint` (SHA-256 of sorted-key JSON) over the question fields, the marking material and the passage list in the student's order. System prompt versions and models are not in it: the reference doesn't depend on how the system answers.
2. **Required knowledge finder (Claude Code, outside the app):** a reverse student. Given the answer key, it works out the knowledge needed to reach that answer and checks each piece against the passages. 3 independent runs (traces) per question, each in a fresh context. Traces run on Claude, not on the group's OpenAI credits. Each trace follows the reference prompt (below) and writes one JSON file.
3. **Merge (code):** `uv run python -m noodles.eval merge <version_id>` combines the 3 traces per question:
   - coverage is `gap` if any trace has a `not in materials` step (sys-design: keep `not in materials` whenever runs disagree);
   - the reference passages are those cited by at least 2 of the 3 traces;
   - the entry keeps each trace's steps, so a disagreement can be traced back to the step and trace that caused it;
   - the entry records the input fingerprint, the trace model and the date, and is then frozen.
4. **Score (code):** `uv run python -m noodles.eval score <version_id>` compares the version's results with the frozen entries. It reads them through the same function as the assessment review (`get_review`), not its own run-log reading: each question's newest result across runs (a per-question rerun replaces only its questions), with the overrides of the run that produced it. It prints a table per question and the totals, and writes the same table as CSV.
   - A question with an entry but no result (not yet test-driven) is listed as "no result" and left out of the rates.
   - For a gap the system missed or added, the table shows the reference step marked `not in materials` (and which traces said so) or the student's `none` step.

### Required knowledge finder prompt

The finder gets the answer key and must trace it to the materials, not solve the question. It uses the student's step rules, so a disagreement reflects coverage, not a different idea of what counts as a step:
- School-level and pre-university knowledge, and anything printed in the question (data, tables, given formulas), need no passage. Every entry has at least one step; one resting only on these is listed with no passages and the reason "general knowledge", as the student's `general_knowledge` step, and is not a gap.
- **Taught in class:** when the question says something was taught in class (e.g. "the normal equations discussed in class") and the answer uses it, knowing it is a step even if the question prints it, judged against the passages up to that week; if they don't teach it, it is `not in materials`. A sub-question that doesn't use it (e.g. one that only asks for a sum from the table) gets no such step. (IS2109 quiz 1: Q1–Q4 covered, Q5–Q6 gaps.)
- **Assumed knowledge:** knowledge the course's entry requirements imply but no passage teaches is listed with no passages and a reason, and is not a gap, as for the student's unreviewed assumptions.
- Each step: the knowledge needed, and the passage IDs that teach it, or `not in materials`.
- "If no passage supports a step, write `not in materials`." No stretched citations.
- Overall `coverage`: `covered` or `gap`.

### Metrics

| Metric | Per question | Reported as |
|---|---|---|
| Coverage agreement (main) | system `gap` flag equals reference `coverage == gap` | agreement rate, plus gaps found, gaps missed and false gaps |
| Answer correctness | the student's effective verdict is `correct` | rate |
| Citation recall (secondary) | distinct reference passages the student also cited (any step), over distinct reference passages | mean over questions with at least one reference passage; "n/a" if there are none |

Report per assessment and in total. Extraction completeness stays optional and isn't in this slice.

Citation recall can be low when the student takes a valid alternative route through other passages (sys-design: secondary metric). It is reported, never used to judge a question wrong.

### Storage

- `data/eval/<course_code>/<version_id>/`: `inputs/`, `traces/`, `reference.json`, `scores.csv`.
- Under `data/`, so never committed: entries contain course passages.
- Scoring refuses an entry whose input fingerprint no longer matches the version (materials or the question changed after it was frozen), and names the question.

## Perturbed set (gold standard)

1. Copy the demo course into a new course code and plant 5 to 10 problems, as in sys-design (delete an explanation, add a question on an untaught topic, reduce a worked example to a mention), plus questions with known AI exposure.
2. A hand-written `labels.json` lists, per question, the expected gap flag and the expected exposure.
3. `score` takes `--labels` in place of the reference set. Metrics: detection rate and false flags, for coverage and exposure separately.
   - Labels are compared with the effective results (overrides applied), as the report shows them. Exposure follows sys-design "Right and wrong": only `correct` counts as right, so a `partial` web answer on a planted exposed question counts as a missed detection.

## Acceptance tests

Fixtures are synthetic; no course materials and no model calls.

- Export writes one input per question with marking material, holding exactly the passages within that question's week limit; a question that already has an entry is skipped.
- Merge marks an entry `gap` when only one trace has a `not in materials` step, and keeps only passages cited by at least 2 traces.
- Score computes coverage agreement, gaps found, missed and false, answer correctness and citation recall on a small hand-built case with known results.
- Score applies verdict overrides and uses each question's latest result across runs.
- Score refuses an entry whose fingerprint no longer matches, naming the question.
- A question with an entry but no result is listed as "no result" and left out of the rates; citation recall with no reference passages is "n/a".
- Export with a prerequisite includes that course's passages, as the student's reach does.
- Score with `--labels` reports detection rate and false flags for coverage and exposure.

## Pilot (user runs)

IS2109 quizzes 1 and 2 (11 questions). Too few to report rates; the pilot checks the trace format, the merge and the scoring end to end. Expect quiz 2 Q3 to Q5 (interaction terms, polynomial regression, dummy variables) as `gap`: none is in Lectures 1 and 2.

## Open

- **Marker accuracy isn't measured.** The reference assumes the marker is right; the true/false bug found on IS2109 marked right answers wrong. A check of the marker's verdicts against the answer key would need its own metric.
- **Trace count:** 3 traces per question is a proposal. Raise it if traces disagree often.
