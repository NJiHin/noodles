# Evaluation: validity, limitations and the IS2109 pilot

How the evaluation runs is in `docs/eval/eval-process.md`; its rules are in `docs/specs/13-evaluation.md`. This file records why the method is a reasonable one, what it can't show, and what the first pilot found. The pilot's data (traces, `reference.json`, `scores.csv`, run logs) are under `data/` and `runs/`, which are never committed, so the numbers are copied here.

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

- **The finder has not been checked against a person.** Every precedent above validates its automated labeller against human labels. Until a person labels a sample (20 to 30 questions) and agreement is reported as Cohen's kappa, a disagreement may be the system's error or the finder's.
- **The finder leans towards gaps.** Working from the answer, it lists more and finer steps than the student; it is told never to stretch a citation; and one trace of three with a `not in materials` step makes a gap. On IS2109 the three traces agreed on every verdict, so the merge rule did not decide anything, but on noisier questions it would.
- **Shared mistakes are invisible.** Where student and finder are wrong the same way, they agree.
- **Only the verdict is compared.** Step-level agreement is not measured; citation recall is the only step-level signal and is secondary.
- **Small sample.** 11 questions (about 7 that need any course knowledge) cannot support rates. The pilot checks that the pipeline works.
- **The student prompt was tuned on the same 11 questions** (see History). Expect lower correctness on unseen questions.

## IS2109 pilot

**Data:** IS2109 (AI and Machine Learning Techniques I), version `23a6e13a375329bf`. Lecture 1 (25 pages, week 1), Lecture 2 (20 pages, week 2). Quiz 1, given in week 1: six numeric blanks on one regression data set (four sums, then the slope and intercept from the "normal equations discussed in class", which the quiz prints). Quiz 2, given in week 2: five true/false statements. All 11 have answer keys.

**Silver set:** 33 finder runs (11 × 3), 22 Oct 2026, Claude Opus 5.5. The three runs agreed on the covered/gap verdict for every question.

**Latest score** (test-drive `20261024T065933837255-e682e7`, student prompt `student-v13`):

| | Value |
|---|---|
| Coverage agreement | 7 / 11 (0.64) |
| Gaps found / missed / false | 2 / 4 / 0 |
| Student answers correct | 11 / 11 |
| Citation recall | 0.50 (over the 4 questions with reference passages) |

| Question | Silver | Noodles | Why |
|---|---|---|---|
| Quiz 1 Q1–Q4 (sums) | covered | covered | Sums of a printed table using printed definitions: one general-knowledge step each. |
| Quiz 1 Q5 (slope), Q6 (intercept) | gap | covered | The quiz says the normal equations were "discussed in class"; Lecture 1 only names them in a chart title and defers regression to weeks 2–3. The student labelled them general knowledge instead of applying the taught-in-class rule. |
| Quiz 2 Q1 (test data in training) | covered | covered | Both cite Lecture 1 p11. |
| Quiz 2 Q2 (overfitting) | gap | covered | Open judgement call: Lecture 1 mentions "overfitting risks" in passing and describes small-k KNN fitting the training data closely without naming overfitting. The finder says that doesn't teach it; the student cited p11 and p23. |
| Quiz 2 Q3 (interaction terms) | gap | gap | Not taught by week 2. |
| Quiz 2 Q4 (polynomial regression is linear) | gap | covered | "Linear means linear in the coefficients" is not taught; the student filed it as general knowledge. |
| Quiz 2 Q5 (five dummy variables) | gap | gap | Dummy coding is not taught by week 2. |

All four misses are the system saying covered where the finder says gap; there were no false gaps.

## History: what the pilot changed

Each finding came from reading a run against the answer keys, then the silver set.

1. **True/false answers were marked wrong when correct.** The code marker needed an exact match, so "False. The test set…" failed against key "F": quiz 2 scored 0/5 for the student although 4 answers were right. Fixed: agents give the bare answer (`final_answer: only "True" or "False"`), the marker matches near-exactly, and an unreadable answer is flagged "Check answer" on the review instead of silently marked wrong.
2. **Wording "Answer only …" made the student drop its steps.** Experiment, 3 runs × 3 questions per variant: steps came back in 8/9 answers when the line named `final_answer`, against 2/9 when a different rule was removed and 0/3 before. Fixed by naming the field.
3. **Aligned-rules experiment (finder).** Giving the finder the student's step rules word for word changed no verdict, except through a first, broad wording of the taught-in-class rule, which made all six quiz 1 blanks gaps (agreement 3/11). The rule was narrowed to apply only when the answer uses the thing taught in class, so the sums (Q1–Q4) stay covered.
4. **Taught-in-class rule added to the student**, so both sides draw the line in the same place. The student applies it inconsistently (one run caught Q5, missed Q6 through a chart-title citation rated `partial`, which by design is not a gap).
5. **No answer without steps.** True/false answers sometimes had no steps, hiding knowledge the student used without declaring it (quiz 2 Q4, Q5). Every answer now has at least one step, and a new `general_knowledge` label covers school-level knowledge or what the question gives: shown in the review, never a gap. This made every miss readable; it did not by itself raise agreement.
6. **Everything stated must come from the question, a tool result or general knowledge,** with the tools listed in the prompt. Before this the student worked out sums in its head inside a step (S_xy = 568 and 475 instead of 493) and got Q5–Q6 wrong; after it, all 11 answers were correct.

Agreement stayed at 7/11 through steps 4–6; correctness went 10/11 → 9/11 → 11/11. Further prompt changes for these four questions were stopped to avoid overfitting to them.

## Known weaknesses and open items

- **Student:** files course knowledge under `general_knowledge` (quiz 2 Q4, quiz 1 Q5–Q6) and applies the taught-in-class rule inconsistently. Recorded as a known weakness; a general fix (a check that general-knowledge steps are really school-level) is to be judged on unseen questions first.
- **Open decision:** does a passage that describes a concept without naming it count as teaching it (quiz 2 Q2)?
- **Not done yet:**
  - the perturbed set;
  - a human check of the finder on 20 to 30 questions, reported as Cohen's kappa;
  - tracing the silver set again with the final finder prompt (its verdicts are unchanged by the later prompt rules, but the stored traces predate them);
  - more weeks of IS2109 and a second course, as unseen questions.
