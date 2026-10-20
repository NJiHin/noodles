# Course Test-Drive: project summary

Working notes for the IS4401 group project (Generative AI Startup). This covers the brief, how the idea developed, the current concept, the literature review, the recommended design, and open decisions. Last updated 2 Oct 2026.

## 1. Project brief (key constraints)

- Due 9 Nov 2026, 11:59 PM. Zip on Canvas, named `GroupX_IS4401_Project_YYYYMMDD.zip`.
- Deliverables:
  - working prototype (public URL or runs locally)
  - Project_Documentation.pdf (8 to 12 pages)
  - 15-minute presentation plus 3-minute Q&A
  - roughly 3-minute demo video
  - slides
  - README with setup instructions
  - peer evaluation on TEAMMATES (3 to 9 Nov)
- The prototype must use at least two of: LLMs, RAG, multi-agent systems, fine-tuning/alignment, image generation.
- No no-code or low-code AI builders (Manus, n8n, Flowith). Use of AI coding tools must be disclosed.
- $40 of OpenAI credits per group. If you use OpenAI, send the group email to Soujanya, cc Gujie, by 10 Oct.
- Rubric (40 marks):

  | Criterion | Marks | Note |
  |---|---|---|
  | Innovation & Creativity | 14 | Weighted most heavily; differentiation from existing solutions is marked explicitly |
  | Business Viability | 10 | |
  | Communication & Presentation | 10 | |
  | Technical Feasibility & Implementation | 6 | |

## 2. How the idea developed

1. **Starting point:** education sector, sold to institutions rather than students, because institutions have budgets. The pain point is updating course materials from semester to semester, especially when a course changes professor.
2. **Split into two problems:** content drift (gradual, easy to put off) and instructor handover (episodic, urgent). We first leaned towards handover as the wedge.
3. **Added semester updates back:** handover alone is too infrequent to justify a recurring subscription.
4. **Advisory only:** the tool does not generate course materials. It only points out problems. Professors stay the authors, which answers the academic-freedom objection, reduces hallucination risk, and sets us apart from content generators.
5. **Problem:** it read as a one-off research agent run at the end of each semester, which is weak for the business case. Adding features (department dashboards, accreditation reports, monitoring) was discussed but rejected. We want one main selling point, not a feature list.
6. **Main idea:** simulated students who "test-drive" the course. Pitch line: **"Test-drive your course before your students do."**
7. **Why now:** students now have AI, so some assessment questions can be answered without taking the course. We dropped an earlier line ("AI is writing the course") because it implies professors misuse AI, which is unsupported and alienates the users. The framing is that AI changes the conditions professors teach under, and the tool supports them.
8. **Dropped:** a "keeping up with the field" agent. It didn't fit the simulated-student idea well.
9. **Back to the original motivation (6 Oct):** the pitch had drifted towards coverage and handover, which are useful but routine. The original concern was the loop where AI writes notes, sets questions and answers them, which raises the question of whether a course teaches anything AI can't. That is now the opening of the story, and the AI-exposure measure is the headline result. Coverage, handover and change impact are supporting scenarios.
10. **Reframed (6 Oct):** "what AI can't teach" is too high a bar, because most content can be learned from AI. A course still offers a structured learning path and assessment that certifies learning. Marks at risk was rejected as a headline, because changing the format brings it to zero. The assessment plan alone was too narrow. **Decision:** the output is a course report whose main section is the assessment review. See `CLAUDE.md` and `sys-design.md`.

## 3. Current concept

**Mission (draft):** help educators keep their courses current, coherent and meaningful to assess as AI changes how students learn.

**What it does:** simulated student agents work through a course in order, using only what the course has taught so far, and attempt its assessments. Where they get stuck, there is a problem in the course. Everything runs on one engine, applied to set scenarios:

| Scenario | What the engine does |
|---|---|
| Verification (core) | Simulated students take the course and its assessments. The report shows where they get lost and which questions are AI-exposed. |
| Professor handover | Test-drive the old course and the new outline, then compare the results: "the new version breaks these 3 things the old one taught." |
| Overlap across courses | One simulated student takes Course A, then Course B, and reports what it already knew and what it was missing. |

**AI-exposure check (two agents take every question):**

| | Generic AI right | Generic AI wrong |
|---|---|---|
| **Course student right** | AI-exposed: answerable without taking the course | Good question: tests what the course taught |
| **Course student wrong** | Tests outside knowledge the course never taught | Broken question, or a gap in the course |

**Graded AI exposure.** A yes/no check doesn't separate questions: an LLM with web search can probably answer almost everything, and solutions to standard textbook-style questions are online and likely in the model's training data. So the generic AI gets web search, to match what students actually have, and the question becomes "what does AI need in order to answer it?":

| Generic AI can answer it... | Exposure |
|---|---|
| With no tools | High: one paste into ChatGPT |
| Only with web search | Exposed, but takes some effort |
| Only with course-specific context (the course's notation, a case discussed in class, a dataset from lecture) | Lower: you need to have taken the course |
| Not even with search | Low |

Expect most questions to be AI-exposed and present that as a valid result. (Updated 6 Oct: AI exposure now feeds the headline result in section 4, and the design uses a single web agent; see `sys-design.md`.)

**Assessment format recommendation.** This combines AI exposure with whether the answer can be looked up in the notes. That comes from the grounding check: a lookup question has its answer almost entirely in one cited passage, while a reasoning question needs several passages and steps.

| | Answer can be looked up in the notes | Needs reasoning beyond the notes |
|---|---|---|
| **AI-exposed** | Closed-book, invigilated | Open-book, invigilated (notes allowed, no internet or AI) |
| **Not AI-exposed** | Closed-book (in any open format it's just a lookup) | Take-home is fine |

- When most of a take-home is exposed, the report may suggest supplements such as an oral defence.
- Recommendations are advisory and phrased as "if AI use isn't intended, consider...". Some take-homes allow AI on purpose, and class size, accessibility and feasibility also affect the choice of format.
- This matches how institutions already sort assessments, e.g. the University of Sydney's "two-lane" approach (secure vs open). Verify before citing.
- It costs almost nothing extra to build: one classification step and one table in the report.

Overlaps between courses fall into three kinds:
- **Intentional build-up:** a later course goes deeper on the same topic.
- **Unnecessary repetition:** the same material at the same depth.
- **Inconsistency:** two courses use different definitions or notation for the same concept.

**Claims to avoid:**
- We do not detect AI-generated content. AI detectors are unreliable, and we check quality whatever the source.
- We do not make tests "AI-proof". We flag AI exposure, and the professor decides what to do.
- We do not predict real student grades or simulate misconceptions. The tool checks whether the course materials support the assessments and the learning path.

## 4. Rubric fit

- **Headline result (6 Oct, superseded the same day by the course report framing; see step 10 in section 2):**
  - The share of a course's assessment that needs **both the course and reasoning**: the student gets it right, the web agent gets it wrong, and the answer isn't a lookup in the notes. For example: "Only 25% of your assessment needs this course and reasoning; AI with web search can answer 60%."
  - Course-specific lookup questions don't count, because they're specific but shallow.
  - If notes, questions and answers all come from AI, this number is low. The tool shows that symptom neutrally, whoever wrote the materials.
  - Limitation: value from attending class (discussion, labs, mentoring) isn't visible in the materials. When most of the assessment is AI-exposed, suggest moving value into what happens in class.
- **Storyline:**
  1. **Why now:** "AI can now write notes, set questions and answer them. How do you know your course still teaches something AI can't?"
  2. **Headline result.**
  3. **How:** week-limited student against a web agent.
  4. **What the professor does next:** fix gaps, change assessment formats, keep the course solid across changes (handover, change impact).
- **Innovation:**
  - Simulated students testing a whole curriculum's structure (sequence, prerequisites, handover, AI exposure) is not something existing work targets. Existing work focuses on tutoring systems, question difficulty and classroom dialogue.
  - The analogy is automated testing in software, applied to courses.
- **Business:**
  - Sold to institutions (department or dean's office), with professors as the users.
  - Subscription justification:
    - **Used throughout the semester, not just at the end.** Professors develop and revise lectures as the term goes on. Each time they draft or improve upcoming content, they can test-drive it against what students have been taught so far, before delivering it. That ongoing demand is the main reason a subscription makes sense.
    - The course map and history become the institution's record of what each course teaches and why. That record is what customers keep paying for, and losing it is a reason not to cancel.
    - Like software tests, it reruns whenever the course changes.
    - Universities already pay annual licences for curriculum and accreditation software that is used only occasionally, e.g. Coursedog, CourseLeaf, Kuali and Watermark. These still need verifying. They handle approval forms and catalogue workflows, while we analyse what is actually taught.
  - Fallback pricing: per course per review.
  - Still needed: survey evidence on how much students use AI for coursework.
- **Communication:** three demo scenes.
  - Semester update: "we changed Week 4, here's what broke."
  - Handover: Prof B's outline compared with Prof A's course.
  - AI-exposure table: "these 4 exam questions are AI-exposed, and here's the format we'd recommend for each."
- **Technical:** RAG (cumulative retrieval index per week) plus multi-agent orchestration (student agents, a generic-AI agent, a grounding checker, a diagnostician). No fine-tuning.

## 5. Literature review

### 5.1 LLMs know too much to pass as students
- [Towards Valid Student Simulation](https://arxiv.org/pdf/2601.05473) (2026): role-play prompting alone is not a valid simulation because LLMs know far more than students. The paper recommends explicitly limiting what the agent knows.
- [Do, Sonkar & Sachan](https://arxiv.org/pdf/2605.12748) (May 2026): simulated students drift towards polished, correct answers ("sycophantic problem solving") instead of keeping their misconceptions. Larger models don't fix this.
- **Implication:** don't promise realistic student errors or misconceptions.

### 5.2 LLMs ignore the context they're given
- [Context-faithful Prompting](https://arxiv.org/abs/2303.11315) (Zhou et al., 2023) and [Parametric knowledge and reading comprehension](https://arxiv.org/pdf/2404.06283) (2024): when given context conflicts with what the model already knows, models tend to fall back on their own knowledge. Better prompting reduces this but doesn't eliminate it.
- **Implication:** "answer only from the course" works only partly as an instruction, so we need a separate check afterwards.

### 5.3 Checking whether claims are supported by sources
- RAGAS faithfulness splits a response into claims and checks whether the context supports each one. FActScore and the AIS framework work similarly.
- [Correctness is not Faithfulness in RAG Attributions](https://arxiv.org/pdf/2412.18004): a correct answer can still be unsupported by its citations.
- **Implication:** our "did it use only taught material" check is an established, measurable technique.

### 5.4 Simulated students for evaluating questions (closest existing work)
- [Generative Students](https://par.nsf.gov/biblio/10519692-generative-students-using-llm-simulated-student-profiles-support-question-item-evaluation) (Lu & Wang, L@S 2024):
  - GPT-4 with 45 profiles, each defined by which knowledge components the student has **mastered, is confused about, or has no evidence of**.
  - Results correlated highly with real students, with considerable overlap in the questions both found hard.
  - **This is the profile format to copy.**
- [Take Out Your Calculators](https://arxiv.org/html/2601.09953v2) (ACL Findings 2026):
  - Open-source models role-play students at four proficiency levels. Question difficulty estimated from their answers (IRT) correlated up to r = 0.82 with real difficulty.
  - Weaker models simulated difficulty better: Gemma 27B did best, while Llama-70B, which answered 92% correctly, did poorly.
  - This needed 300 simulated students per question and local GPUs, and only estimated aggregate difficulty. Models still matched real students' wrong answers only 31 to 47% of the time.
  - Going from 100 to 300 students added little.
- [EduAgent and Agent4Edu](https://arxiv.org/html/2501.10332v1) ([code](https://github.com/bigdata-ustc/Agent4Edu), AAAI 2025): predict individual learners' quiz performance. A different goal from ours.
- Other student and classroom simulators: [SimClass](https://aclanthology.org/2025.naacl-long.520/), [Classroom Simulacra](https://arxiv.org/pdf/2502.02780), [MathVC](https://murongyue.github.io/MathVC.github.io/), [StudentSim](https://huggingface.co/papers/2609.01591), [SimLearner](https://github.com/abigail-gh/simlearner), [sim-student-eval](https://github.com/umass-ml4ed/sim-student-eval) (ACL 2026; realism metrics).
- [Machine unlearning for novice students](https://arxiv.org/html/2603.26142v1): removes Python knowledge from Mistral-7B with LoRA. We rejected this because it is fine-tuning, and every course would need its own model.

### 5.5 Automatically extracting the concepts taught and tested
- LLM tagging of knowledge components is a mature research area: [KC generation from MCQs](https://arxiv.org/pdf/2405.20526), [KCluster](https://arxiv.org/pdf/2505.06469), [coding-problem KCs](https://arxiv.org/html/2502.18632v2), [evidence-grounded competency tagging](https://link.springer.com/chapter/10.1007/978-3-032-29744-0_41).
- **Implication:** building the course map rests on proven methods.

### 5.6 Swarm simulators
- [MiroFish](https://github.com/666ghj/MiroFish) (AGPL-3.0, built on OASIS), [OASIS](https://github.com/camel-ai/oasis), [Generative Agents](https://github.com/joonspk-research/generative_agents), [TinyTroupe](https://github.com/microsoft/TinyTroupe), [AgentSociety](https://github.com/tsinghua-fib-lab/AgentSociety/).
- These model social dynamics: agents influencing each other's opinions. Learning a course doesn't depend on students interacting, so a swarm adds cost without making the simulation more valid. A small set of profiles is enough.
- MiroFish's document-to-persona pipeline is a useful pattern, but its AGPL licence brings obligations if we copy its code.

### 5.7 Caveats about the review
- This was one sweep of searches and abstracts, not a full reading of every paper, and some summaries came from automated page extraction.
- Before citing in the documentation, read Generative Students, Take Out Your Calculators, Do et al. and RAGAS in full.

## 6. Recommended design

**Principle:** don't try to make the model know less. Check whether it used only what the course taught. The agent using outside knowledge is not a failure to fix. Once the check catches it, it is the finding we want to report.

Decisions:
- **No fine-tuning:** it costs too much, and unlearning doesn't carry over to new courses.
- **No weak models:** they get things wrong unpredictably, cite poorly, and don't reliably admit when they don't know. Their errors wouldn't tell us anything about the course.

Pipeline:
1. **Course map:** extract the concepts taught each week (with supporting passages) and the concepts each question needs, using the mastered / confused / unknown format.
2. **Student profiles:** 4 to 6 profiles defined by prerequisites and level, not personality. Examples: "met all prerequisites", "missing prerequisite X", "transfer student without course Y". Level sets how explicitly a concept must be taught before the student can use it: merely mentioned, or explained with a worked example. Personas are cosmetic, for the demo only.
3. **Constrained attempt:** gpt-4.1-mini answers using only retrieved content from weeks 1 to N plus its prerequisites. It cites a passage for every step and says "not taught" when it finds no support.
4. **Grounding check:** a separate call sees only one step and its cited passage, not the question or the final answer, and decides whether the passage supports the step. A correct answer with unsupported steps still counts as a gap.
5. **Retry (optional):** when a step is flagged, the agent gets one retry using only the passages.
   - If it still succeeds, the outside knowledge was a shortcut, so the issue is low severity.
   - If it fails, the question really needs untaught material, so the issue is high severity.
6. **Generic-AI runs:** the same model answers with no tools, then with web search, then with course-specific context. This gives the graded exposure level. Combined with the lookup-or-reasoning classification from the grounding check, it produces the assessment format recommendation.
7. **Coverage check from the course map:** if a question needs concept X and no week up to that point teaches it, flag it. This doesn't depend on the agents at all.
   - If both checks flag it, confidence is high.
   - If only one flags it, the professor reviews it.
8. **Handover:** run the pipeline on both versions of the course and compare the results.

Failure modes:

| Failure | Fix |
|---|---|
| The check accepts a step its passage doesn't support | Keep the check in an isolated call; measure its accuracy on 30 to 50 hand-labelled steps |
| False "not taught" because retrieval missed the material | Search again using the concept's name; confirm against the course map before flagging |

**Prompt development:** use the pilot-then-freeze approach from the assignment.
1. Tune the prompts on a development course with planted problems.
2. Freeze the prompts, model and settings.
3. Report results only from a different test course with different planted problems.

## 7. Cost estimate

Assumes one course with 60 questions and 6 profiles, using gpt-4.1-mini at about $0.40 input / $1.60 output per million tokens (third-party aggregator figure; confirm on OpenAI's pricing page).

| Item | Estimate |
|---|---|
| Student attempts (360, at about 4k input / 600 output tokens each) | about $0.95 |
| Grounding checks | about $1 |
| Generic-AI run and concept extraction | under $1 |
| **One full course run** | **about $2 to $3** |
| Handover comparison | double a full run |

- The $40 covers roughly 10 to 15 full runs including development, provided we pilot on a few questions first and cache results.
- The Batch API roughly halves the cost.
- gpt-4.1-nano (about 4 times cheaper) could handle concept extraction. Keep the student agent and the check on mini.
- Credit limits only become a problem if we copy the 300-agent setups from the psychometrics papers. In our design, results don't depend on the number of agents.

## 8. Data sources

**Background knowledge (decided).** Higher-level courses build on earlier ones, so the student answers from this course (weeks 1 to N) plus its prerequisite courses' materials. The grounding check sorts each step by where its support comes from: this course, a prerequisite course, or general knowledge at the course's level. A step supported by none of these is flagged, either as a gap or as an undeclared prerequisite. Course descriptions alone (NUSMods) aren't enough, because they don't show what was actually taught.

**Demo scope: two paths from two NUS courses, using actual course materials shared with the professors' approval.**
- **Path 1:** a level-1 course with no prerequisites, tested on course knowledge only.
- **Path 2:** a level-2 course with exactly one prerequisite, tested with that prerequisite course's materials as background. Ideally the level-1 course is that prerequisite, so two courses' materials cover both paths.
- Future work: courses with several prerequisites, textbook fallbacks (OpenStax) for prerequisites without materials, confidence levels by background source, and whole-school curriculum graphs. At institutional scale this data comes from the LMS.

Other sources:

- **NUS course materials (with approval):** slides, notes and assessments for the two demo courses. Use them only with the professors' explicit permission, store them privately (not in a public repo), and credit them as agreed.
- **NUSMods API:** prerequisites and preclusions for NUS courses. Useful to confirm the prerequisite link between the two demo courses. Descriptions alone don't show what was taught.
- **Planted problems:** delete a prerequisite lecture, add questions on untaught topics, copy topics between courses. This gives us ground truth for evaluation.
- **In the real product,** the institution connects its LMS (for example through the Canvas API), so data collection is only a prototype issue.

## 9. Evaluation plan

The tool doesn't claim to simulate how real students think or what mistakes they make. Its claim is that a student who had only these materials would get stuck here. Three levels of evaluation test that claim:

1. **Does it find real problems? (main result)**
   - Detection rate and false-flag rate on problems planted in the NUS demo courses.
   - Baseline: a single LLM reads the whole course and lists problems.
   - Ablation: turn off the grounding check and measure how often the agent uses outside knowledge.
   - Accuracy of the grounding check on hand-labelled steps.
2. **Do instructors agree with the flags? (if we can get TAs or professors)** 2 to 3 TAs or professors rate about 20 flags from an unmodified course as "real problem", "minor" or "not a problem".
3. **Does it get stuck where real students get stuck? (evidence it matches real students)** A mini-course study:
   - Write 2 to 3 short lessons on a topic participants won't know, with a deliberate gap.
   - 10 to 20 classmates read the lessons, take the quiz and mark whether each question was covered.
   - Compare their results with the agents' flags.
   - This works because we control exactly what participants were taught.
   - Get consent and collect no personal data. Present the results as indicative only.

For any AI-exposure evaluation, use new or paraphrased questions wherever solutions may already be published online.

## 10. Prototype scope (about 5 weeks)

- **Must build:**
  - the test-drive engine
  - the graded AI-exposure check and assessment format recommendation
  - handover comparison
- **Stretch:** overlap across courses (the two demo courses can be used for this).
- **Future work:** in-semester monitoring, department dashboard, accreditation reports.

Rough timeline:

| When | Work |
|---|---|
| By 10 Oct | Send the group email for OpenAI credits |
| Week 1 | Lock the framing, get approval and materials for the two NUS courses, user interviews |
| Weeks 2 and 3 | Course map and RAG pipeline, student agents, grounding check |
| Week 4 | Handover comparison, AI-exposure check, UI (Streamlit), evaluation runs |
| Week 5 | Documentation, slides, demo video, buffer |

## 11. Q&A preparation

- **"Why not generate the updates too?"** Professors own their content, and a tool that rewrites it won't get adopted. Finding the problems is the slow part, and that's what we automate.
- **"Aren't LLMs too smart to act like students?"** Yes, so we don't rely on them behaving like students. We check every step against the course materials. When an agent uses outside knowledge, that is the gap we report.
- **"Is this a one-off tool?"** No. Professors use it throughout the semester to test upcoming lectures and revisions before delivering them. The course record it builds up also becomes more valuable each semester.

## 12. Open items

- Research competitors properly (Coursedog, CourseLeaf, Kuali, Watermark; Open Syllabus) for the market analysis.
- Find survey evidence on how much students use AI on coursework.
- Choose the two NUS courses, get the professors' approval, and agree how the materials may be used and credited.
- Decide how to split development and test sets (e.g. different weeks or different planted problems) when there are only two courses.
- Decide whether to add persona flavour for the demo.
- Check what assessments come with the course materials, and write additional questions if there aren't enough.
