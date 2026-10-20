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

The professor uploads all their files. The week for each file is guessed from its filename, and the professor confirms it. Assessments are uploaded with their answers or marking material, and the professor states which weeks each one covers (its `week_cutoff`) and its `current_format`.

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
6. **Passages:** one page or slide is one passage, with ID `<course>-w<week>-<file slug>-p<page>` (e.g. `CS1010-w5-slides-p12`). The file slug comes from the filename and is unique within a version, so two files in the same week can't collide. Written to the course store with its `origin` (`parser` or `vlm`).

- Whole pages, not crops: no crop coordinates, no table border check, and nothing is clipped or missed when an element isn't detected.
- Thresholds for "very little text" and "mostly garbled" are set during the build, checked on the demo courses.
- Setup outside `uv sync`: LibreOffice, Java 11+ (for OpenDataLoader) and Ollama with `qwen3-vl:2b` (about 1.9 GB).
- Before relying on it, run one slide deck and one Word document from each demo course through the pipeline and check the flagged pages by eye.

**Assessments into questions:**
1. Assessment and answer files go through the same parsing pipeline, but are written to the separate assessments table (see Course store), never to `passages`.
2. One LLM call per assessment splits the parsed paper and its answers into question records: question ID, question text, options (if any), type and that question's marking material. Each sub-part (1a, 1b) is its own question.
3. Code checks (fail loudly, flag for the professor):
   - each question's text appears verbatim in the parsed paper
   - every question has marking material and every piece of marking material has a question
4. The professor confirms or corrects the question list before any run, like the week guess.

- Cached in the run log, so it reruns only when the files change.

## Stage 1: course map (extraction)

**Goal:** turn a course's weekly materials into a course map: topics, the depth each is taught at in each week, and supporting passages. Every later stage reads from this map.

**Pipeline (MVP):**
1. **Passages (from stage 0):** one passage per page or slide, with stable IDs that include the course code (e.g. `CS1010-w5-slides-p12`), so citations are unambiguous when a prompt contains two courses. Passages are written to the course store (see Orchestration and storage).
2. **Parallel extraction:** one LLM call per week, each seeing only its own week's passages with their IDs. Output is a list of concept records (format below), not a summary.
3. **Orchestrator:** one LLM call receives all the weekly records and regroups them by topic. It merges duplicates, picks the standard name (the most precise term, not the earliest) and keeps other names as aliases.
   - If the course has a previous reviewed version, its concepts (`concept_id`, name, aliases, from `concepts`) are injected as a reference for merging only: reuse an existing ID when a topic is the same, and add new concepts freely when a new topic is found.
   - In map review, code lists the IDs that disappeared and the IDs that are new since the previous version, so a rename that slipped through shows up as one of each and the professor fixes it.
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

**Updates:** when a week is edited, only that week's extractor call reruns (the others are cached by fingerprint). The orchestrator reruns with the previous version's concepts as reference (step 3), so concept IDs stay stable across versions. Do a full rebuild once per semester.

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
  - **Code questions:** excluded from the MVP. No agent runs on them, and the report lists them as "not assessed (code question)". Running them against test cases is on the roadmap.
  - **No answer key:** run coverage and grounding only. Report AI exposure as "not assessed". Don't generate model answers.
  - The marker and the grounding checker are both LLM judges with custom prompts. No evaluation framework.

**Retrieval (agentic, over the topic index):** chosen over injecting all the notes, because materials can include textbooks and overflow the context, and over embedding search on the question, because questions are worded as tasks and match the notes poorly.
- **Topic list in the system prompt:** one line per topic from the reviewed map, limited to topics with an occurrence up to week N, plus the prerequisite course's topics:
  ```
  CS1010:recursion | recursion (also: recursive functions) | Introduced via a Fibonacci example.
  ```
- **Lookup tool:** `lookup_concept(topic_ids)`. `topic_ids` is an enum of the listed IDs, so the student can't ask for a topic that doesn't exist. Code returns every passage tagged with those topics from weeks up to N (and the prerequisite), each with its passage ID and contextual heading.
- **Calling is optional:** zero calls is valid. If no listed topic fits, the student answers with what it has and labels the steps `none` or `assumed_knowledge`. Up to about 5 calls per question, capped in code.
- **Re-check of uncited steps:** a single pass after the student answers, not a loop. This catches topics the student overlooked and passages the extractor never tagged.
  1. For each `none` or `assumed_knowledge` step, code runs one FTS5 keyword search using the step's claim, over passages within the week limit (headings included, so aliases match). Each word of the claim is quoted, since raw text like "n = 2k + 1" is invalid FTS5 syntax.
  2. Steps with no hits keep their label, with no call.
  3. If any steps have hits, code continues the student's own conversation with one more message holding the found passages for those steps. The student returns corrected labels for them (each may become `course` or `prerequisite` with evidence), seeing the question and its other steps. One call per question, and the unchanged conversation prefix is billed at the cached rate.
- The week limit is enforced in code: the agent never sees anything after week N.
- **N** is the `week_cutoff` of the assessment (e.g. a Week 6 quiz gives N = 6; the final exam covers all weeks). The professor states it when uploading the assessment and its answers.
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
  - `assumed_knowledge`: must give a one-line reason, or the `accepted_id` of an accepted claim
  - `none`: no source
- Use `prerequisite` whenever the material exists there. Use `assumed_knowledge` only when it doesn't.
- **The student's system prompt must state the difference between `assumed_knowledge` and `none` explicitly:**
  - `assumed_knowledge`: something implied by the course's stated entry requirements (e.g. A-level maths, or the prerequisite course) that isn't in the provided materials. It must come with a one-line reason.
  - `none`: subject knowledge the answer needs that the student wouldn't already know and can't find in the course or prerequisite materials.
  - Include a short example of each in the prompt, and tell the agent to choose `none` when it's unsure.
- **Decided claims in the prompt:** the student's system prompt lists the course's assumed-knowledge decisions, each with its ID:
  - accepted: the student may rely on them. A step that does is labelled `assumed_knowledge` with `"accepted_id": <id>` instead of a reason.
  - rejected: students are not assumed to know these. A step that needs one is labelled `none`.
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

**Answer key:**
- for each question (from the split in stage 0):
  - the professor's existing marking material, in whatever form they have it (correct option, model answer, rubric). No required format. Any marks it states stay in it as context for the marker.
  - the assessment it belongs to
- for each assessment, entered by the professor at upload: `week_cutoff` and `current_format` (take-home / online quiz / invigilated exam)

**How each source is checked:**

| `source` | Checked by | In the report |
|---|---|---|
| `course`, `prerequisite` | Grounding checker | An unsupported step becomes a gap |
| `none` | Professor | Main findings: a gap or a missing prerequisite |
| `assumed_knowledge` | Professor (light review) | Low-priority section, "assumed, not yet confirmed". Not counted as a gap until rejected. |

Professor decisions are saved (in `assumed_knowledge`, see Course store) and given to the student in later runs (see Student output):
- **accepted:** the student cites it by `accepted_id`, and the step is skipped in review
- **rejected:** the student labels that knowledge `none`, so it becomes a gap
- A claim the student doesn't recognise as decided comes back to the professor as new. The worst case is reviewing it twice, never a wrong skip.
- Each decision changes the student's prompt, so the next run reruns the student on every question. Professors should finish a review before rerunning.

**Gap (code), per question:** a question has a gap if any of these holds:
- a step is `none` (including knowledge the professor rejected)
- a `course` or `prerequisite` step is `unsupported` by the grounding checker

A grounding `partial` is shown as a weak citation, not a gap. Unreviewed `assumed_knowledge` is not a gap.

**Right and wrong:** only a `correct` verdict counts as right; `partial` and `incorrect` count as wrong. The report still shows the actual verdict.

**AI exposure (code):**

| | Web agent right | Web agent wrong |
|---|---|---|
| **Student right** | AI-exposed | Good: depends on course-specific context |
| **Student wrong** | Needs knowledge that's neither taught nor declared | Broken question, or a gap |

**Lookup or reasoning (code):** the number of the student's knowledge steps. One or fewer is lookup; two or more is reasoning. Steps list only knowledge brought in, with pure reasoning folded in (see Student output), so the count measures how much knowledge had to be combined. A heuristic, stated under Limitations.

**Recommendation rules (code):** applied in order, first match wins.

| # | Evidence | Recommendation |
|---|---|---|
| 1 | Gap | **Fix coverage first,** then reassess |
| 2 | No answer key | AI exposure "not assessed", no format recommendation |
| 3 | Student wrong, web right | **Review:** needs knowledge that's neither taught nor declared |
| 3 | Student wrong, web wrong | **Review:** the question may be broken |
| 4 | Student right, web wrong | **Keep it open or take-home:** it already certifies learning |
| 5 | AI-exposed, lookup | **Closed-book, invigilated** |
| 5 | AI-exposed, reasoning | **Open-book invigilated**, or redesign it to use course-specific material |

- Code questions skip all rules and are reported as "not assessed (code question)".
- Both rule 5 lines add: "or, if it must stay open, add a check: oral defence, staged submissions or an in-class component". The professor chooses.
- If the recommendation matches `current_format`, report "keep as is".
- The value is in knowing which questions can stay open, not in putting everything under invigilation.
- Wording is advisory, e.g. "if AI use isn't intended, consider...".

**Roadmap:** "what if" scenarios, e.g. a student who hasn't taken prerequisite X (for waivers and students from other faculties). Same agent, with that prerequisite's materials removed.

## Stage 4: course report

Combined in code from the stage 2 and 3 outputs and the course map:
1. **Summary:** verdict, key figures, top actions.
2. **Assessment review (main):** for each assessment and question: coverage, AI exposure, lookup or reasoning, and a recommendation (see Recommendation rules).
3. **Learning path:** gaps, concepts only mentioned but assessed, concepts taught but never assessed. Each question's concepts are worked out in code from the student's citations: each cited passage maps to the concept records that list it as evidence. There is no separate question-mapping step. Limitation (stated in the report): a concept used only in an `assumed_knowledge` or `none` step isn't counted as assessed, and a cited passage tagged with several concepts counts all of them. **Only mentioned but assessed:** every topic has a `depth` for each occurrence (week), set by the extractor in stage 1. For each concept a question uses (found from the student's citations), take its deepest level in any week up to the question's `week_cutoff`. If that is only `mentioned`, flag it, e.g. "the final exam relies on the call stack, only mentioned in week 5, slide 13". The grounding checker can't catch this, because a passing mention still supports the step. Depth labels are the extractor's judgement, and a light mention may be intentional, so this is reported for the professor to consider, not as an error. "Ordering problems" (a concept used before it's taught) are not a separate finding: the student never sees later weeks, so these appear as `none` flags and the professor recognises them in review.
4. **Assumed knowledge to confirm.**
5. **Changes since the last run:** compares this run with the latest run of the previous version, in code. Both levels:
   - **Questions** (matched by `question_id`): changes in student verdict, web verdict, AI exposure, gap and recommendation. A question whose text changed is marked "question edited".
   - **Course map** (matched by `concept_id`): topics added or removed, and depth changes per week.
   - **Navigation:** the section opens with counts per kind of change, and each entry links to that question or topic. Changed items also carry a marker in the assessment review and learning path, showing before → after.
   - On a course's first version, the section says there is no previous run.
6. **Method and limitations.**

## Orchestration and storage

**Run order for one course:**
1. Ingestion and course map (weekly extractors in parallel, then the orchestrator). Runs once per version of the course.
2. Professor review of the map. The run waits here.
3. For each question, with questions running in parallel:
   1. the student agent (with its topic lookups) and the web agent run at the same time
   2. the re-check: keyword search on each uncited step, then at most one continued student call
   3. the grounding checker runs on each cited step (checks in parallel)
   4. the marker runs once per final answer (student and web agent marked in separate calls)
4. The report is assembled in code.

**Implementation:**
- Plain Python with `asyncio` and the OpenAI SDK.
- No agent framework, because the flow is fixed. The only choice an agent makes is which topics the student looks up, handled by a small tool-call loop in code.
- A few calls at once, to stay within rate limits, with automatic retries on failure.
- OpenAI structured outputs (JSON schemas) for every agent.
- **Models** (all at reasoning effort `none`, so temperature 0 can be set):
  - `gpt-6-luna`: weekly extractors, question split, student agent, re-check, grounding checker, marker
  - `gpt-6-sol`: orchestrator (one call per course, and every later stage depends on the map)
  - `gpt-6-sol` with the Responses API `web_search` tool: web agent. A weak model would underrate AI exposure, since it stands in for a student using AI.

**Course-level versioning:**
- The course code is the ID that groups all versions of a course (e.g. `CS1010`).
- Every re-upload or week correction creates a new version (identified by a fingerprint of its materials and their confirmed weeks) under the same course code. A handover is a new version uploaded by a different professor.
- "Changes since the last run" compares the latest version with the previous one under the same course code.
- The cache is shared across all versions of a course, so unchanged weeks reuse earlier results.

**Run log (cache and trace):**
- One JSONL file per run (`runs/<course_code>/<version>/<run_id>.jsonl`). The first line is the run configuration (target version, prerequisite version). Then one record per call: the fingerprint of its inputs, the call type, the question ID, the token usage (and web-search calls) and the full output. Cached results add no cost.
- Written as each call finishes, so an interrupted run resumes where it stopped.
- **Fingerprint = a hash of the content the call can see**, plus the prompt version and model. Not the course version, so a call reruns only when its own inputs change:
  - student agent: the question, the topic list, the decided assumed-knowledge claims, and every passage (text and heading) it could look up, i.e. target weeks 1 to N plus the prerequisite. A map edit changes the topic list and headings, so it reruns.
  - web agent: the question only
  - re-check: the student's conversation plus the found passages
  - grounding checker: the step and its cited passages
  - marker: the question, the marking material and the final answer
- At the start of a run, earlier records under the same course code are loaded by fingerprint. Identical inputs reuse the stored result, so editing week 4 reruns only questions with `week_cutoff` of 4 or later.
- The record stores the fingerprint, not the full prompt. The materials are stored once, in the course store.
- Web agent results depend only on the question, so they're reused when the materials change.
- The report or dashboard reads from the run log.
- **Cost reporting:** each run reports its actual cost (tokens per call type and web-search calls, summed from the run log). No up-front estimate.

**Course store (SQLite):**
- One SQLite file for the whole project (`data/noodles.db`). Every course and version lives in it as rows keyed by `version_id`.
- Written at ingestion (materials, assessments), after the question split, and after professor review (map, headings). Agent calls write to the run log, not here.

```sql
-- Courses and versions
CREATE TABLE courses (
  code TEXT PRIMARY KEY                       -- e.g. CS1010
);

CREATE TABLE versions (
  id TEXT PRIMARY KEY,                        -- fingerprint of the materials and their confirmed weeks
  course_code TEXT NOT NULL REFERENCES courses(code),
  created_at TEXT NOT NULL,
  map_reviewed_at TEXT                        -- NULL until the professor confirms the map
);

-- Stage 0: course materials (the only content the student can reach)
CREATE TABLE files (
  version_id TEXT NOT NULL REFERENCES versions(id),
  slug TEXT NOT NULL,                         -- unique within a version; used in passage IDs
  filename TEXT NOT NULL,
  week INTEGER NOT NULL,                      -- professor-confirmed
  PRIMARY KEY (version_id, slug)
);

CREATE TABLE passages (
  version_id TEXT NOT NULL,
  passage_id TEXT NOT NULL,                   -- e.g. CS1010-w5-lecture05-p12
  file_slug TEXT NOT NULL,
  week INTEGER NOT NULL,
  page INTEGER NOT NULL,
  text TEXT NOT NULL,
  origin TEXT NOT NULL CHECK (origin IN ('parser', 'vlm')),
  heading TEXT,                               -- contextual heading, rebuilt after map review
  UNIQUE (version_id, passage_id),
  FOREIGN KEY (version_id, file_slug) REFERENCES files(version_id, slug)
);

CREATE VIRTUAL TABLE passages_fts USING fts5(
  heading, text, content='passages'           -- keyword re-check, BM25
);

-- Stage 1: reviewed course map (professor edits these rows directly)
CREATE TABLE concepts (
  version_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,                   -- e.g. CS1010:recursion, stable across versions
  name TEXT NOT NULL,
  aliases TEXT NOT NULL DEFAULT '[]',         -- JSON array
  description TEXT,
  PRIMARY KEY (version_id, concept_id)
);

CREATE TABLE occurrences (
  version_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  week INTEGER NOT NULL,
  depth TEXT NOT NULL CHECK (depth IN ('mentioned', 'explained', 'worked_example', 'practised')),
  PRIMARY KEY (version_id, concept_id, week)
);

CREATE TABLE evidence (                       -- this IS the passage-to-topic index
  version_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  passage_id TEXT NOT NULL,
  PRIMARY KEY (version_id, concept_id, passage_id),
  FOREIGN KEY (version_id, passage_id) REFERENCES passages(version_id, passage_id)
);
CREATE INDEX evidence_by_passage ON evidence (version_id, passage_id);

-- Assessments (never read by student-facing queries)
CREATE TABLE assessments (
  version_id TEXT NOT NULL,
  assessment_id TEXT NOT NULL,                 -- e.g. week6-quiz
  week_cutoff INTEGER NOT NULL,
  current_format TEXT NOT NULL CHECK (current_format IN ('take_home', 'online_quiz', 'invigilated_exam')),
  PRIMARY KEY (version_id, assessment_id)
);

CREATE TABLE assessment_files (               -- parsed paper and answers, input to the split
  version_id TEXT NOT NULL,
  assessment_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('paper', 'answers')),
  filename TEXT NOT NULL,
  text TEXT NOT NULL
);

CREATE TABLE questions (                      -- output of the split, professor-confirmed
  version_id TEXT NOT NULL,
  question_id TEXT NOT NULL,                  -- e.g. q07, q07a
  assessment_id TEXT NOT NULL,
  text TEXT NOT NULL,
  options TEXT,                               -- JSON array, NULL if none
  type TEXT NOT NULL CHECK (type IN ('mcq', 'true_false', 'short', 'numeric', 'open', 'code')),
  marking_material TEXT,                      -- NULL = no answer key
  PRIMARY KEY (version_id, question_id)
);

-- Professor decisions
CREATE TABLE assumed_knowledge (              -- per course, so it carries across versions
  id INTEGER PRIMARY KEY,                     -- cited by the student as accepted_id
  course_code TEXT NOT NULL REFERENCES courses(code),
  claim TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected')),
  decided_at TEXT NOT NULL
);

CREATE TABLE verdict_overrides (              -- tied to one run; a rerun's new answers have none
  run_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  agent TEXT NOT NULL CHECK (agent IN ('student', 'web')),
  verdict TEXT NOT NULL CHECK (verdict IN ('correct', 'partial', 'incorrect')),
  PRIMARY KEY (run_id, question_id, agent)
);
```

- **Run inputs:** `:target` (a version of the course under test), `:prereq` (the prerequisite course's latest version with `map_reviewed_at` set, or none) and `:n` (the question's `week_cutoff`).
- **Week limit:** `(version_id = :target AND week <= :n) OR version_id = :prereq`, applied to topic-list, lookup and re-check queries. The prerequisite is never cut by week.
- **Student-facing queries** read only `passages`, `passages_fts`, `concepts`, `occurrences` and `evidence`. The assessment tables never appear in them (enforced in code).
- **FTS sync:** `passages_fts` is external-content, so code runs `INSERT INTO passages_fts(passages_fts) VALUES('rebuild')` after ingestion and after every heading rebuild.
- Foreign keys are enforced (`PRAGMA foreign_keys = ON` on every connection), so evidence can't point at a passage from another version.
- **Map corrections** edit `concepts`, `occurrences` and `evidence` directly. The orchestrator's draft stays in the run log.
- **Derived fields** (week introduced, deepest depth up to a cutoff) are calculated from `occurrences` in queries, never stored.
- No embeddings and no vector extension.
- No server: Python's built-in `sqlite3` opens it. `data/` is never committed.
- The run log stays JSONL. SQLite is for data the system queries; the log is written once and read in order.

**Users:** one user, no auth.

**UI (decided):** a FastAPI backend with a React front end, chosen so the look and feel of the dashboard can be fully customised. The backend runs the pipeline and serves results from the run log, and the front end shows the course report as a dashboard. The API, screens and how long-running jobs report progress are defined in the slice specs.

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
- Questions without an answer key are left out.
- Metrics:
  - **coverage agreement** (main): the gap or no-gap verdict for each question matches the reference
  - **answer correctness**
  - **citation recall** (secondary): a valid alternative route can lower it without being wrong
  - optionally, **extraction completeness**
- AI exposure isn't part of the reference. It's covered by the perturbed set.
- Name it a silver standard and state its limitations. It comes from a different model family (Claude) from the system (OpenAI GPT-6 Luna and Sol), which reduces the risk of a model favouring its own reasoning.

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
- **Code questions:** run the student's and web agent's code against test cases.
- **Topic dependencies** (`uses`) and a prerequisite graph, if a later feature needs them.
- **Metamorphic self-tests:**
  - remove a worked example, and that concept's depth should go down
  - delete the explaining passage, and the topic should no longer be "explained"
  - point evidence at a wrong passage, and the checker should reject it
  - shuffle week order, and the map should stay the same
- **Local NLI model** instead of the LLM for the evidence checker, to save API credits.
- **Known limitation:** there are no hand labels, so there is no absolute measure of extraction accuracy.
