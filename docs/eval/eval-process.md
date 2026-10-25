# How the evaluation works

A plain walkthrough of the reference-set evaluation. The rules and file formats are in `docs/specs/13-evaluation.md`; the design is in `docs/sys-design.md` ("Evaluation"); why the method is valid, its limitations and the IS2109 pilot results are in `docs/eval/eval-findings.md`.

## The idea

The system's student works forwards: from the question, through the course materials, to an answer, and says which steps the materials don't teach (a gap). To check it, the **required knowledge finder** works backwards: it is given the answer key, works out the knowledge needed to reach that answer from the question, and checks each piece against the course passages (taught by which passages, or not in the materials). A reverse student, run with a stronger model. Then we compare the two.

Its results, frozen per question, are the **silver set**: made by a model, not a person, so a strong reference rather than the truth.

## Before you start

- The course is uploaded, its course map confirmed, and each week's quiz confirmed with its answer key.
- A test-drive has run on those quizzes.
- Each quiz's week is the week it was given, so it is traced only against the materials up to that week.

## Steps

**1. Export the inputs (code, free).**

```
uv run python -m noodles.eval export <version_id>
```

For every question with an answer key, this writes one file holding the question, its answer key, every passage the student could read by that quiz's week, and the instructions for the trace. Add `--prerequisite <course_code>` if the test-drive used one. Questions already in the silver set are skipped.

**2. Run the required knowledge finder three times per question (Claude Code).**

Three separate runs read each input file, each in a fresh context, so no run sees another's answer. Each run lists the knowledge the answer needs, step by step, and for each step either the passages that teach it or `not in materials`. The finder follows the student's step rules: school-level knowledge and anything printed in the question need no passage (an answer resting only on these gets one general-knowledge step), and something the question says was taught in class is a step whenever the answer uses it. Each run writes one file to `traces/` (a run's output is called a trace). These runs don't use the OpenAI credits.

**3. Merge into the silver set (code, free).**

```
uv run python -m noodles.eval merge <version_id>
```

For each question with three traces:
- it is a **gap** if any trace found a step `not in materials`;
- its **reference passages** are those at least two of the three traces cited;
- the entry is **frozen**: it never changes, and all three traces are kept so a disagreement can be explained later.

**4. Score the test-drive against it (code, free).**

```
uv run python -m noodles.eval score <version_id>
```

For each question it compares the system's latest result (the one the assessment review shows, overrides included) with the frozen entry, and reports:
- **coverage agreement** (the main number): do the system and the silver set agree on gap or no gap? Split into gaps found, gaps missed and false gaps;
- **answer correctness**: did the student get it right;
- **citation recall**: how many of the reference passages the student also cited. Secondary: a valid different route can lower it.

Each disagreement shows why: the step the traces said isn't taught, or the student's step behind its gap. The table is also written to `scores.csv`.

**5. Read the disagreements.**

A disagreement is either a system miss or a judgement call about what "taught" means (a passing mention, a concept described but not named). Decide which; if it is a judgement call, add a line to the trace instructions and trace those questions again.

## Each new week

Upload the week's lecture and quiz, rebuild and confirm the course map, run the test-drive, then repeat steps 1 to 4. Only the new quiz's questions are exported and traced; earlier entries stay frozen.

If an earlier week's file or page text changes, its quizzes' entries no longer match and scoring refuses them, naming the questions. Delete those entries from `reference.json` and their files in `traces/`, then repeat steps 1 to 3 for them.

## Where the files are

`data/eval/<course_code>/<version_id>/`: `inputs/`, `traces/`, `reference.json`, `scores.csv`. Under `data/`, so never committed: they contain course passages.

## The perturbed set (gold standard)

A second check with known answers: copy the course, plant problems on purpose (remove an explanation, add a question on an untaught topic, add questions copied from the web), and write down what should be flagged in a `labels.json`. Then:

```
uv run python -m noodles.eval score <version_id> --labels labels.json
```

reports how many planted problems were caught and how many false flags were raised, for coverage and AI exposure separately.
