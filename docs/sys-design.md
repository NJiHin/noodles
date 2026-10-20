# System design

This file is the single source of truth for the design.

## Product

**Pitch:** "Test-drive your course before your students do."

**Problem:** AI has made information easy to get. What a course still offers is a structured learning path, and assessment that shows students actually learned the material. Professors can't easily tell whether both still work: whether the materials support the assessments, and whether AI can answer those assessments without the course.

**What it does:** a simulated student, limited to the course's materials up to each assessment's week, attempts every question and cites a passage for each step. A web-search agent attempts the same questions. Comparing the two, and checking each step against the materials, produces a **course report centred on a review of the assessments**: coverage gaps, AI exposure, and advisory recommendations (keep open, change format, redesign, or add a check). The value is in knowing which questions can stay open, not in putting everything under invigilation.

**Customer and users:**
- **Customer:** the institution (department or dean's office).
- **Users:** professors.
- **Why a subscription:** professors run it throughout the semester as they draft or revise lectures and assessments, and when a course changes hands. The course record it builds up becomes more useful every semester.

**Storyline:**
1. **Why now:** with AI, information is easy to get. Does the course's learning path still hold together, and does its assessment still show learning?
2. **Output:** a course report, centred on the assessment review.
3. **How:** a student limited to the course content, week by week, compared with a web-search agent.
4. **What it suggests:** assessment changes, fixes for coverage gaps, and consistency across changes (handover, edits).
5. **What it doesn't do:** rewrite materials or force decisions. The professor decides.

**Claims to avoid:**
- Detecting AI-generated content.
- Making tests "AI-proof".
- Predicting grades or simulating misconceptions.
- Measuring the value of attending class.
- Implying that professors misuse AI.

**Demo scope:** two NUS courses, used with the professors' approval:
- a level-1 course with no prerequisites
- a level-2 course with one prerequisite, ideally the level-1 course

**GenAI areas (the brief requires at least two):**
- **Use of LLMs:** prompt and context engineering (the persona, source definitions, the week-limited topic list), structured outputs, and LLM judges (marker and grounding checker).
- **Multi-agent systems and orchestration:** parallel weekly extractor agents with an orchestrator agent that combines their output (stage 1), then the student agent, web agent, grounding checker and marker, each with a defined role and defined access to information (stages 2 and 3).
- **RAG:** agentic retrieval over an LLM-built topic index. The student looks up topics through a tool call and gets back the tagged passages, and a keyword re-check over the raw passages catches untagged material (see Retrieval below).

## Stage 0: ingestion

The professor uploads all their files. The week for each file is guessed from its filename, and the professor confirms it. Assessments are uploaded with their answers or marking material, and the professor states which weeks each one covers (its `week_cutoff`).

**Parsing pipeline (one route for every file type):**
1. **Upload:** `.pptx`, `.docx` and `.pdf`. Legacy `.ppt`/`.doc` are rejected with a request to re-save. Speaker notes and spreadsheets are left out.
2. **Convert:** LibreOffice (headless) turns Office files into PDF. PDFs pass through unchanged.
3. **Parse:** OpenDataLoader (fast mode only) extracts each page's text in reading order, and lists each element's type (image, table, heading, paragraph) with its page number.
4. **Flag a page** if any of these holds:
   - it has an image or a table
   - it has very little text (likely a diagram drawn from shapes)
   - its text is mostly garbled characters (likely equations)
   - it has vector drawings (shape count from pypdfium2), which catches diagrams drawn from shapes that have many labels
5. **Transcribe flagged pages:** pypdfium2 renders the whole page to an image, and Qwen3-VL 2B (one model, via Ollama, on the machine running the backend) returns the page as markdown: tables as markdown tables, equations as LaTeX, and diagrams described, covering only what's visible. Its output replaces the parser's text for that page and is marked `origin: vlm`. The report says when a step relies on a `vlm` passage.
6. **Passages:** one page or slide is one passage (e.g. `CS1010-w5-slides-p12`), written to the course store with its `origin` (`parser` or `vlm`).

- Whole pages, not crops: no crop coordinates, no table border check, and nothing is clipped or missed when an element isn't detected.
- Thresholds for "very little text" and "mostly garbled" are set during the build, checked on the demo courses.
- Setup outside `uv sync`: LibreOffice, Java 11+ (for OpenDataLoader) and Ollama with `qwen3-vl:2b` (about 1.9 GB).
- Before relying on it, run one slide deck and one Word document from each demo course through the pipeline and check the flagged pages by eye.

## Stage 1: course map (extraction)

**Goal:** turn a course's weekly materials into a course map: topics, the depth each is taught at in each week, and supporting passages. Every later stage reads from this map.

**Pipeline (MVP):**
1. **Passages (from stage 0):** one passage per page or slide, with stable IDs that include the course code (e.g. `CS1010-w5-slides-p12`), so citations are unambiguous when a prompt contains two courses. Passages are written to the course store (see Orchestration and storage).
2. **Parallel extraction:** one LLM call per week, each seeing only its own week's passages with their IDs. Output is a list of concept records (format below), not a summary.
3. **Orchestrator:** one LLM call receives all the weekly records and regroups them by topic. It merges duplicates, picks the standard name (the most precise term, not the earliest) and keeps other names as aliases.
4. **Professor review:** the professor confirms or corrects the map before the test-drive runs.
5. **Index and contextual headings (code):** after review, reverse the merged map's `evidence` lists into a passage-to-topic index, and give each passage a contextual heading built from it (course, week, file, and its topics' standard names and aliases). Both are stored in the course store and rebuilt whenever the map changes. Passages no topic claimed get a heading without topics.

**Contextual heading** (stored with each passage):

```
[CS1010 | Week 5 | Lecture: Recursion | Topics: recursion (also: recursive functions); memoisation]
[CS1010-w5-slides-p12] A recursive function calls itself on a smaller input...
```

**Weekly extractor output** (one record per topic per week):

```json
{ "name": "recursion", "description": "Introduces recursion via a Fibonacci example.", "depth": "worked_example", "evidence": ["CS1010-w5-slides-p12", "CS1010-w5-slides-p14"] }
```

**Merged map** (one record per topic, produced by the orchestrator):

```json
{
  "concept_id": "CS1010:recursion",
  "name": "recursion",
  "aliases": ["recursive functions"],
  "description": "Introduced via a Fibonacci example, practised in week 7.",
  "occurrences": [
    { "week": 5, "depth": "worked_example", "evidence": ["CS1010-w5-slides-p12", "CS1010-w5-slides-p14"] },
    { "week": 7, "depth": "practised", "evidence": ["CS1010-w7-tutorial-p3"] }
  ],
  "course": "CS1010"
}
```

- `depth` is one of `mentioned`, `explained`, `worked_example`, `practised`, recorded for each occurrence (each week).
- `description` is one optional line in the extractor's own words. The notes don't need to state a definition.
- `course` is the actual course code. Whether a course is the target or a prerequisite is a property of the run, not the topic: the run configuration records it (e.g. "target: CS2030, prerequisites: CS1010").
- `concept_id` includes the course code and stays the same across versions of the course.
- Add fields only when a later stage needs them. `definition`, `notation` and `uses` were dropped.

**Derived fields (calculated when needed, never stored):**
- week introduced: the earliest occurrence
- weeks revisited: the other occurrences
- deepest level up to a question's `week_cutoff`: the highest `depth` among occurrences up to that week

Calculating these on demand keeps them in step with the map after a professor corrects it. The passage-to-topic index is the exception: retrieval needs it on every lookup, so it's stored (step 5) and rebuilt whenever the map changes.

**Updates:** when a week is edited, re-extract only that week and match its topics to the existing concept IDs, so comparisons between versions stay stable. Do a full rebuild once per semester.

## Stage 2 and 3: test-drive and verification

**Agents (each question):**
- **Student agent:** runs once per question with a single profile, the **intended student**: "You have completed [the course's stated prerequisites] and attended weeks 1 to N of this course. You know nothing else in this subject." Gets the topic list for weeks 1 to N plus the prerequisite course, and retrieves passages through a lookup tool (see Retrieval below). There are no mastery levels and no year-based persona.
- **Web agent:** runs once. LLM with web search, standing in for a student using AI to answer.
- **Grounding checker:** a code check, then an isolated LLM call. Verifies `course` and `prerequisite` steps only.
- **Marker:** gives each final answer a verdict (`correct` / `partial` / `incorrect`) and a one-line reason. Marking only feeds the exposure table. Coverage and grounding don't depend on it.
  - **Multiple choice and true/false:** exact match in code.
  - **Short answer, numeric and open-ended:** an LLM marker. It sees the question, the professor's marking material and one final answer. It doesn't see the steps, and it doesn't know which agent wrote the answer.
  - **Phrasing bias, handled without engineering:**
    - the marker accepts the professor's existing marking material in any format (model answer, rubric, marking scheme), passed through as is with no restructuring
    - the marker is told to ignore phrasing, length and style, and to judge meaning against the marking material, whatever its form
    - both agents are told to answer concisely, as in an exam
    - the professor can override any verdict in the report
  - **Code questions:** roadmap (run against test cases).
  - **No answer key:** run coverage and grounding only. Report AI exposure as "not assessed". Don't generate model answers.
  - The marker and the grounding checker are both LLM judges with custom prompts. No evaluation framework.

**Retrieval (agentic, over the topic index):** chosen over injecting all the notes, because materials can include textbooks and overflow the context, and over embedding search on the question, because questions are worded as tasks and match the notes poorly.
- **Topic list in the system prompt:** one line per topic from the reviewed map, limited to topics with an occurrence up to week N, plus the prerequisite course's topics:
  ```
  CS1010:recursion | recursion (also: recursive functions) | Introduced via a Fibonacci example.
  ```
- **Lookup tool:** `lookup_concept(topic_ids)`. `topic_ids` is an enum of the listed IDs, so the student can't ask for a topic that doesn't exist. Code returns every passage tagged with those topics from weeks up to N (and the prerequisite), each with its passage ID and contextual heading.
- **Calling is optional:** zero calls is valid. If no listed topic fits, the student answers with what it has and labels the steps `none` or `assumed_knowledge`. Up to about 5 calls per question, capped in code.
- **Re-check of uncited steps (code):** before a `none` or `assumed_knowledge` step is accepted, code runs an FTS5 keyword search using the step's claim, over all passages up to week N (headings included, so aliases match). If it finds passages, the student gets them and re-checks that one step, which may become `course` or `prerequisite`. If it finds nothing, the label stands. This catches topics the student overlooked and passages the extractor never tagged.
- The week limit is enforced in code: the agent never sees anything after week N.
- **N** is the `week_cutoff` of the assessment component (e.g. a Week 6 quiz gives N = 6; the final exam covers all weeks). The professor states it when uploading the assessment and its answers.
- Put the topic list first and the question last, so questions with the same `week_cutoff` share a cached prompt prefix (OpenAI charges cached input at a lower rate).

**Student output (the steps are shown to the professor):**

```json
{
  "question_id": "q07",
  "week_cutoff": 6,
  "final_answer": "B",
  "steps": [
    { "step_id": "q07-s1", "claim": "A recursive function needs a base case.", "source": "course", "evidence": ["CS1010-w5-slides-p12"] },
    { "step_id": "q07-s2", "claim": "Rearranging gives n = 2k + 1.", "source": "assumed_knowledge", "reason": "The entry requirement is A-level maths, which covers basic algebra." },
    { "step_id": "q07-s3", "claim": "Memoisation caches results.", "source": "none" }
  ]
}
```

- No `status` field. Coverage comes from the steps (any `none` step is a gap) and correctness from the marker, so the student can't contradict itself.
- `final_answer` is `null` if the student can't attempt the question; it still lists the steps it managed.
- `source` is one of:
  - `course`: must cite passages from weeks 1 to N
  - `prerequisite`: must cite passages from the prerequisite course
  - `assumed_knowledge`: must give a one-line reason
  - `none`: no source
- Use `prerequisite` whenever the material exists there. Use `assumed_knowledge` only when it doesn't.
- **The student's system prompt must state the difference between `assumed_knowledge` and `none` explicitly:**
  - `assumed_knowledge`: something implied by the course's stated entry requirements (e.g. A-level maths, or the prerequisite course) that isn't in the provided materials. It must come with a one-line reason.
  - `none`: subject knowledge the answer needs that the student wouldn't already know and can't find in the course or prerequisite materials.
  - Include a short example of each in the prompt, and tell the agent to choose `none` when it's unsure.
- List only steps that bring in knowledge. Fold pure reasoning into those steps' claims.
- Don't include a self-reported confidence field.

**Web agent output:** `question_id`, `final_answer`, `sources` (URLs).

```json
{
  "question_id": "q07",
  "final_answer": "B",
  "sources": [
    "https://en.wikipedia.org/wiki/Recursion_(computer_science)",
    "https://docs.python.org/3/library/functools.html#functools.cache"
  ]
}
```

**Grounding checker output:** for each step, `step_id`, `verdict` (`supported` / `partial` / `unsupported`) and `reason`.

```json
{
  "step_id": "q07-s1",
  "verdict": "supported",
  "reason": "The passage states that every recursive function needs a base case to stop."
}
```

**Single run per agent (deliberate limitation):** each agent runs once per question at temperature 0. Repeated runs would reduce noise but triple the cost and add merging logic. This isn't warranted for the MVP, and is consistent with common LLM-as-judge practice. Stated under Limitations in the report and the documentation.

**Answer key:** for each question:
- the professor's existing marking material, in whatever form they have it (correct option, model answer, rubric). No required format.
- the assessment component it belongs to, and that component's `week_cutoff`
- `current_format` (take-home / online quiz / invigilated exam)
- `must_stay_open` (yes/no, for projects and reports)
- an optional `intended_approach`, used to flag correct answers reached by an unintended route
- optional marks

**How each source is checked:**

| `source` | Checked by | In the report |
|---|---|---|
| `course`, `prerequisite` | Grounding checker | An unsupported step becomes a gap |
| `none` | Professor | Main findings: a gap or a missing prerequisite |
| `assumed_knowledge` | Professor (light review) | Low-priority section, "assumed, not yet confirmed". Not counted as a gap until rejected. |

Professor decisions are saved:
- **accepted:** the item goes on the course's assumed-knowledge list and is skipped in future runs
- **rejected:** the item becomes a gap in future runs

**AI exposure (code):**

| | Web agent right | Web agent wrong |
|---|---|---|
| **Student right** | AI-exposed | Good: depends on course-specific context |
| **Student wrong** | Needs knowledge that's neither taught nor declared | Broken question, or a gap |

- Exposure, combined with lookup versus reasoning (how many passages and steps the student needed), gives the advisory format recommendation.

**Recommendation rules (code):**

| Evidence | Recommendation |
|---|---|
| Not AI-exposed, needs reasoning | **Keep it open or take-home:** it already certifies learning |
| AI-exposed, lookup or recall | **Closed-book, invigilated** |
| AI-exposed, reasoning that doesn't depend on the course | **Open-book invigilated**, or redesign it to use course-specific material |
| AI-exposed and `must_stay_open` | **Add a check:** oral defence, staged submissions or an in-class component |
| Coverage gap (whatever the exposure) | **Fix coverage first,** then reassess |

- If the recommendation matches `current_format`, report "keep as is".
- The value is in knowing which questions can stay open, not in putting everything under invigilation.
- Wording is advisory, e.g. "if AI use isn't intended, consider...".
- Include web-search tool fees in the cost estimate.

**Roadmap:** "what if" scenarios, e.g. a student who hasn't taken prerequisite X (for waivers and students from other faculties). Same agent, with that prerequisite's materials removed.

## Stage 4: course report

Combined in code from the stage 2 and 3 outputs and the course map:
1. **Summary:** verdict, key figures, top actions.
2. **Assessment review (main):** for each component and question: coverage, AI exposure, lookup or reasoning, intended method, and a recommendation (keep / change format / redesign / add a check).
3. **Learning path:** gaps, concepts only mentioned but assessed, concepts taught but never assessed. Each question's concepts are worked out in code from the student's citations: each cited passage maps to the concept records that list it as evidence. There is no separate question-mapping step. **Only mentioned but assessed:** every topic has a `depth` for each occurrence (week), set by the extractor in stage 1. For each concept a question uses (found from the student's citations), take its deepest level in any week up to the question's `week_cutoff`. If that is only `mentioned`, flag it, e.g. "the final exam relies on the call stack, only mentioned in week 5, slide 13". The grounding checker can't catch this, because a passing mention still supports the step. Depth labels are the extractor's judgement, and a light mention may be intentional, so this is reported for the professor to consider, not as an error. "Ordering problems" (a concept used before it's taught) are not a separate finding: the student never sees later weeks, so these appear as `none` flags and the professor recognises them in review.
4. **Assumed knowledge to confirm.**
5. **Changes since the last run.**
6. **Method and limitations.**

## Orchestration and storage

**Run order for one course:**
1. Ingestion and course map (weekly extractors in parallel, then the orchestrator). Runs once per version of the course.
2. Professor review of the map. The run waits here.
3. For each question, with questions running in parallel:
   1. the student agent (with its topic lookups) and the web agent run at the same time
   2. the re-check runs on each uncited step
   3. the grounding checker runs on each cited step (checks in parallel)
   4. the marker runs once per final answer (student and web agent marked in separate calls)
4. The report is assembled in code.

**Implementation:**
- Plain Python with `asyncio` and the OpenAI SDK.
- No agent framework, because the flow is fixed. The only choice an agent makes is which topics the student looks up, handled by a small tool-call loop in code.
- A few calls at once, to stay within rate limits, with automatic retries on failure.
- OpenAI structured outputs (JSON schemas) for every agent.

**Course-level versioning:**
- The course code is the ID that groups all versions of a course (e.g. `CS1010`).
- Every re-upload creates a new version (identified by a fingerprint of its materials) under the same course code. A handover is a new version uploaded by a different professor.
- "Changes since the last run" compares the latest version with the previous one under the same course code.
- The cache is shared across all versions of a course, so unchanged weeks reuse earlier results.

**Run log (cache and trace):**
- One JSONL file per run (`runs/<course_code>/<version>/<run_id>.jsonl`), with one record per call: the fingerprint of its inputs (prompt version, model, content), the call type, the question ID and the full output.
- Written as each call finishes, so an interrupted run resumes where it stopped.
- At the start of a run, earlier records are loaded by fingerprint. Identical inputs reuse the stored result, so editing week 4 reruns only questions with `week_cutoff` of 4 or later.
- Store a reference to the course content (the course version's fingerprint plus `week_cutoff`), not the full prompt. The materials are stored once.
- Web agent results depend only on the question, so they're reused when the materials change.
- The report or dashboard reads from the run log.

**Course store (SQLite):**
- One SQLite file per course version (`data/<course_code>/<version>/course.db`), holding:
  - `passages`: passage ID, course, week, file, text and `origin` (`parser` / `vlm`), written at ingestion
  - the merged course map, the passage-to-topic index and each passage's contextual heading, written after professor review
  - an FTS5 table over headings and text, for the keyword re-check (BM25 ranking)
- The week limit is a SQL filter (`course IN (target, prerequisite) AND week <= N`), applied to both lookups and the re-check.
- No embeddings and no vector extension.
- No server: Python's built-in `sqlite3` opens it. `data/` is never committed.
- The run log stays JSONL. SQLite is for data the system queries; the log is written once and read in order.

**UI (decided):** a FastAPI backend with a React front end, chosen so the look and feel of the dashboard can be fully customised. The backend runs the pipeline and serves results from the run log, and the front end shows the course report as a dashboard.

## Evaluation

Required for the documentation's Evaluation section: test cases or metrics, a baseline comparison, examples and edge cases.

**1. Perturbed set (gold standard): tests that flagging works.**
- One demo course with 5 to 10 planted coverage problems, e.g. delete an explanation, add a question on an untaught topic, reduce a worked example to a passing mention.
- Add a few questions with known AI exposure: some copied from public sources (should be exposed) and some about a specific case from the course (shouldn't be).
- The labels come from how each problem was planted.
- Metrics: detection rate and false flags, for coverage and exposure separately.

**2. Reference set (silver standard): tests the whole pipeline on an unmodified course.**
- Generated once by Claude Code with a strong model. For each question it receives the question, **the answer key** and the same week-limited materials as the student agent.
- Its task is to **trace the known answer to the materials**, not to solve the question. For each step it records the knowledge needed, the supporting passage IDs or `not in materials`, and an overall coverage verdict. Optionally it also lists the topics taught in each week, which lets us measure extraction completeness.
- Run several times and merged (an LLM may do the merging), keeping `not in materials` whenever runs disagree. Then frozen.
- The prompt forbids stretching citations: "if no passage supports a step, write `not in materials`".
- Follow `intended_approach` where one is given. Questions without an answer key are left out.
- Metrics:
  - **coverage agreement** (main): the gap or no-gap verdict for each question matches the reference
  - **answer correctness**
  - **citation recall** (secondary): a valid alternative route can lower it without being wrong
  - optionally, **extraction completeness**
- AI exposure isn't part of the reference. It's covered by the perturbed set.
- Name it a silver standard and state its limitations. It comes from a different model family (Claude) from the system (GPT-4.1-mini), which reduces the risk of a model favouring its own reasoning.

**3. Live demo:** the final presentation runs on the presenting professor's own course notes, with their approval.
- Results are prepared in advance and served from the run log, not run live.
- Review the report beforehand.
- Collect one line of feedback from the professor afterwards, as user feedback.

**4. Documentation examples:** 2 to 3 dashboard screenshots from the evaluation runs, including one false flag as the edge case.

**Q&A to prepare:** "If a strong model can build the reference, why do we need the product?" Building it took repeated runs, merging and checking: a one-off research effort, not something a professor can do weekly. The product does it in one repeatable, week-limited run, and adds AI exposure, recommendations, change tracking and the dashboard.

## Roadmap (build if time allows, otherwise list as future work)

- **Telemetry:** self-hosted Langfuse, or LangSmith with non-sensitive data only. Both can wrap the plain OpenAI SDK, with no LangChain needed. Developer debugging and cost per run only. The report still comes from the run log.
- **Embedding grouping before the orchestrator,** for larger courses where the orchestrator's input gets too long.
- **Code merge checks:** each record in exactly one group; flag merges of records the same week listed separately; flag weak or near-duplicate groups; names appear in the cited passages; output is the same when rerun or when week order is shuffled.
- **Topic dependencies** (`uses`) and a prerequisite graph, if a later feature needs them.
- **Metamorphic self-tests:**
  - remove a worked example, and that concept's depth should go down
  - delete the explaining passage, and the topic should no longer be "explained"
  - point evidence at a wrong passage, and the checker should reject it
  - shuffle week order, and the map should stay the same
- **Local NLI model** instead of the LLM for the evidence checker, to save API credits.
- **Known limitation:** there are no hand labels, so there is no absolute measure of extraction accuracy.
