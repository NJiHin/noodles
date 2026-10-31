# Evaluation: validity, limitations and results

How the evaluation runs is in `docs/eval/eval-process.md`; its rules are in `docs/specs/13-evaluation.md`. This file records why the method is a reasonable one, what it can't show, and what the IS2109 runs and the perturbed set found. The pilot's data (traces, `reference.json`, `scores.csv`, run logs) are under `data/` and `runs/`, which are never committed, so the numbers are copied here.

## What is being evaluated

The report's main claim per question is a verdict: **covered** (the course up to that week teaches what the question needs) or **gap**. The evaluation checks that verdict, plus whether the student's answer is right. It does not check the student's individual steps or reasoning (decided 24 Oct 2026: verdict only).

## Why the method is reasonable

No single published method does exactly this, but each part has an established counterpart.

| Part | Counterpart | What the literature says |
|---|---|---|
| Required knowledge finder: the knowledge each question needs | **Q-matrix / knowledge-component tagging** in educational measurement: an item-to-skill map, usually written by experts | Expert Q-matrices are subjective and are validated statistically ([Culpepper 2019](https://par.nsf.gov/servlets/purl/10099070); [Sachdeva](https://academiccommons.columbia.edu/doi/10.7916/D8JQ2HF1)). GPT-4-generated knowledge components matched human labels on 56% (Chemistry) and 35% (E-Learning) of questions, and experts preferred the LLM's about two-thirds of the time ([Moore et al. 2024](https://arxiv.org/pdf/2405.20526); also [KCGen-KT](https://arxiv.org/html/2502.18632v1)). |
| Finder: checking each piece against what was taught | **Curriculum–assessment alignment studies** (Webb's criteria) | An established procedure, normally run by expert panels ([NRC, *Keeping Score*](https://www.nationalacademies.org/read/9635/page/72)). |
| Calling the frozen reference "silver" | **Silver-standard corpora** (biomedical NLP) | References built by automated systems; scores partly measure agreement with other automated systems, not with the truth ([CALBC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3239301/)). |
| A model's judgement in place of a person's | **LLM-as-a-judge** | GPT-4 agreed with human preferences over 80% of the time, about as often as humans with each other ([Zheng et al. 2023](https://arxiv.org/abs/2306.05685)); agreement depends on the judge being able to answer the question itself ([arXiv 2503.05061](https://arxiv.org/pdf/2503.05061v2)). Chance-corrected agreement (Cohen's kappa) is preferred over raw agreement. |
| Perturbed set: planted problems | **Fault injection / mutation testing** | Accepted practice; planted faults can be easier or harder to find than real ones ([Andrews, Briand et al. 2005](https://personal.utdallas.edu/~lxz144130/cs6301-readings/andrews-icse05.pdf)). |
| The student agent | **LLM student simulation** | Simulated item difficulty correlated 0.75–0.82 with national test statistics ([Acquaye et al.](https://arxiv.org/pdf/2601.09953)); a known issue is that LLMs know too much to play a limited student ([Towards Valid Student Simulation](https://arxiv.org/pdf/2601.05473)). |
| Working backwards from a given answer | **Rationalization** in STaR ([Zelikman et al. 2022](https://arxiv.org/pdf/2203.14465)) | Knowing the answer invites after-the-fact justification, one reason the finder may over-list steps. |

Design choices that follow this literature: the finder runs on a different model family (Claude) from the system (GPT-6 Luna and Sol), to reduce a model favouring its own reasoning; it runs three times per question, independently; it is frozen before comparison; and the perturbed set supplies labels that are known by construction.

## Limitations

- **The finder has not been checked against a person.** Every precedent above validates its automated labeller against human labels; a human check (Cohen's kappa on 20 to 30 questions) is out of scope for this project. A disagreement may be the system's error or the finder's.
- **The finder leans towards gaps.** Working from the answer, it lists more and finer steps than the student; it is told never to stretch a citation; and one trace of three with a `not in materials` step makes a gap. On IS2109 the three traces agreed on every verdict (32 questions), so the merge rule did not decide anything, but on noisier questions it would.
- **Shared mistakes are invisible.** Where student and finder are wrong the same way, they agree.
- **Only the verdict is compared.** Step-level agreement is not measured; citation recall is the only step-level signal and is secondary.
- **Small sample.** 32 questions from one course, with 2 reference gaps. Rates are indicative only; gap detection in particular rests on 2 cases.
- **The student prompt was tuned on 11 of the 32 questions** (quizzes 1 and 2; see History). The other 21 were unseen.
- **Week cutoffs are an input.** A cutoff one week early turns taught material into gaps on both sides (see History, item 7). The evaluation can't detect a wrong cutoff by itself.
- **One run per course.** Run-to-run variation isn't measured, so a single changed verdict may be noise.
- **The perturbed set was planted by Claude**, so its results also measure the planting; three plants had to be fixed (see Perturbed set).

## IS2109 results

**Data:** IS2109 (AI and Machine Learning Techniques I), version `23a6e13a375329bf`. Lectures 1 to 11 (weeks 1 to 11; Lectures 6 and 7 are one file in week 6). Quizzes 1 to 9, 32 questions, all with answer keys. Each quiz tests the lecture after its number, so its week cutoff is that lecture's week: quiz 1 → 2, quiz 2 → 3, quiz 3 → 4, quiz 4 → 5, quiz 5 → 6, quiz 6 → 6, quiz 7 → 8, quiz 8 → 9, quiz 9 → 10. No quiz covers week 11; the week 10 quiz is a reflection with no answer key and is left out.

**Silver set:** 96 finder runs (32 × 3), 27–28 Oct 2026, Claude Opus 5.5, with the current finder prompt. The three runs agreed on the covered/gap verdict for every question. 30 questions are covered, 2 are gaps.

**Latest score** (test-drive `20261031T031211958109-8d4468`, student prompt `student-v14`, marker on Sol; the previous run, `20261028T015402157820-afbee3` with `student-v13` and the marker on Luna, is shown for comparison):

| | Previous | Latest |
|---|---|---|
| Coverage agreement | 29 / 32 (0.91) | 30 / 32 (0.94) |
| Gaps found / missed / false | 0 / 2 / 1 | 0 / 2 / 0 |
| Student answers correct | 28 / 32 (0.88) | 30 / 32 (0.94) |
| Citation recall | 0.45 | 0.45 |
| AI exposure | 28 exposed, 3 web only right, 1 both wrong | 30 exposed, 1 web only right, 1 both wrong |

Disagreements:

| Question | Silver | Noodles | Why |
|---|---|---|---|
| Quiz 2 Q3 (interaction terms) | gap | covered | The hierarchical principle (keep the main effects when a model has an interaction term) is not stated; Lecture 3's examples follow it without saying it. |
| Quiz 9 Q2 (PCA) | gap | covered | That principal components are uncorrelated is not taught; Lecture 10 shows how the second component is built but never states it. |

Quiz 3 Q2 (precision, recall, F1), a false gap in the previous run, now cites Lecture 4 and agrees.

Wrong answers: quiz 6 Q2 (regression tree salary; key 6.00, student 84.125; both agents wrong) and quiz 8 Q2 (confidence of {Beer} → {Coke}; student 2/3, key 1/3, a real error). Quiz 1 Q5 and quiz 5 Q2b, wrong in the previous run, are now right.

## Perturbed set results

**Data:** IS2109P, a copy of IS2109 (version `35fa893d3b29bb08`) with planted problems and 13 questions; labels in `data/eval/IS2109P/35fa893d3b29bb08/labels.json`. A label is set only where it is known by construction; otherwise it is `null` and left out of that metric. The 32 original questions were removed: their gap labels would only repeat the silver set, and nothing labels their exposure.

**Plants:**

| Kind | Questions | Expected |
|---|---|---|
| Explanation deleted | Laplace smoothing (quiz 4 Q2) | gap |
| Worked example cut to a mention | precision/recall/F1 (quiz 3 Q2), Gini (quiz 6 Q1) | gap |
| Topic never taught | DBSCAN core point (new) | gap |
| Topic taught after the cutoff | k-means centroid update in quiz 4 (new; k-means is week 8) | gap |
| Copied from a public source | ISLR Ch. 3 Ex. 3 and Ch. 4 Ex. 6a, 6b (new) | AI-exposed |
| Needs the lecturer's own results | confusion matrix vs accuracy, K-means plots, shopper segments (new) | covered; course-specific |
| Public fact the course never uses | mean Sales in ISLR Carseats (new) | gap; web only right |
| Wrong answer key | entropy of 6 Yes / 6 No, key 0.5 (new) | covered; both wrong |

**Score** (test-drive `20261031T030833847919-cf9e12`, same prompts and marker as the latest IS2109 run):

| | Result |
|---|---|
| Coverage gaps caught | 5 / 6, no false gaps on 5 controls |
| AI-exposed | 3 / 3 |
| Course-specific | 2 / 3 |
| Web only right | 1 / 1 |
| Both wrong | 1 / 1 |

Misses:
- **Precision/recall/F1 (gap missed).** The student cited a page that names the metrics without the formulas. The grounding checker rated it `partial` ("does not state the formulas"), and by design a `partial` citation is a weak citation, not a gap.
- **K-means plots (course-specific → both wrong).** The student repeated the slide's own claim that WCSS "reaches a minimum" at k = 3; the marker rated it `partial`, which counts as wrong.

Fixes made to the plants after the first run, each a planting mistake, not a system result: a two-part question lost the data in its first part; two "course-specific" questions turned out to be ISLR's own analyses (Default ROC, Advertising VIFs), which the web agent found, so they were removed, not relabelled.

Lessons: a question is course-specific only when the data is the lecturer's own, not when a public data set or analysis is reused. IS2109 builds almost every example on textbook data (ISLR, Han & Kamber, Tan et al.), so most of its questions are AI-exposed, as the system reports.

## History: what the pilot changed

Each finding came from reading a run against the answer keys, then the silver set.

1. **True/false answers were marked wrong when correct.** The code marker needed an exact match, so "False. The test set…" failed against key "F": quiz 2 scored 0/5 for the student although 4 answers were right. Fixed: agents give the bare answer (`final_answer: only "True" or "False"`), the marker matches near-exactly, and an unreadable answer is flagged "Check answer" on the review instead of silently marked wrong.
2. **Wording "Answer only …" made the student drop its steps.** Experiment, 3 runs × 3 questions per variant: steps came back in 8/9 answers when the line named `final_answer`, against 2/9 when a different rule was removed and 0/3 before. Fixed by naming the field.
3. **Aligned-rules experiment (finder).** Giving the finder the student's step rules word for word changed no verdict, except through a first, broad wording of the taught-in-class rule, which made all six quiz 1 blanks gaps (agreement 3/11). The rule was narrowed to apply only when the answer uses the thing taught in class, so the sums (Q1–Q4) stay covered.
4. **Taught-in-class rule added to the student**, so both sides draw the line in the same place. The student applies it inconsistently (one run caught Q5, missed Q6 through a chart-title citation rated `partial`, which by design is not a gap).
5. **No answer without steps.** True/false answers sometimes had no steps, hiding knowledge the student used without declaring it (quiz 2 Q4, Q5). Every answer now has at least one step, and a new `general_knowledge` label covers school-level knowledge or what the question gives: shown in the review, never a gap. This made every miss readable; it did not by itself raise agreement.
6. **Everything stated must come from the question, a tool result or general knowledge,** with the tools listed in the prompt. Before this the student worked out sums in its head inside a step (S_xy = 568 and 475 instead of 493) and got Q5–Q6 wrong; after it, all 11 answers were correct.

Agreement stayed at 7/11 through steps 4–6; correctness went 10/11 → 9/11 → 11/11. Further prompt changes for these four questions were stopped to avoid overfitting to them.

7. **The week cutoffs were one week early.** With quizzes 3 to 9 added, the finder marked almost every question a gap and often noted the topic was "next lecture". Matching each quiz's topics to the lecture that teaches them showed each quiz tests the lecture after its number. Cutoffs were corrected (quiz 7 by two weeks, quiz 6 unchanged), and the silver set and test-drive were redone. The 11-question pilot's 7/11 and its four misses (items 1 to 6) were measured with the wrong cutoffs: under the corrected ones, the normal equations, overfitting and "linear in the coefficients" are taught, and all four now agree.
8. **The student had no label for missing information** (perturbed set). Asked for a data value neither given nor taught, it labelled the step `general_knowledge` and wrote "I cannot calculate it", so no gap was raised. `none` now covers "subject knowledge or information" not in the question or materials (`student-v14`).
9. **The marker gave identical answers opposite verdicts** (perturbed set). With a wrong key, the student's "1 bit" was marked wrong and the web agent's "1 bit" right, once with the reason "matching the marking material". A rule that the key is authoritative (`mark-v2`) did not fix it on Luna; moving the marker to Sol did. Sol is stricter: it marks an answer `partial` when it adds a wrong claim.

Items 8 and 9 were rerun on IS2109: no new false gaps, and agreement and correctness both rose (see the score table).

## Known weaknesses and open items

- **Student:** misses gaps where the materials show a rule by example without stating it (quiz 2 Q3) or leave out one property (quiz 9 Q2). The earlier `general_knowledge` pattern (course knowledge filed as general knowledge) no longer appears: its cases are taught by the corrected cutoffs, so it is untested rather than fixed.
- **`partial` citations are never gaps.** In the perturbed set the grounding checker named the missing knowledge but the rule kept it from being a gap (precision/F1; Laplace was also missed this way in an earlier run). Whether a `partial` whose reason says the key claim is missing should count as a gap is undecided.
- **Answers:** 2 wrong answers on covered questions (quiz 6 Q2, quiz 8 Q2).
- **Answers marked only by styling** (coloured or bold options) are lost at parsing; see `docs/sys-design.md` (Known bug). Quiz 4's keys were typed in by hand.
- **Not done yet:** a second course, as unseen questions; repeated runs to measure run-to-run variation.
