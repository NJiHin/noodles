# 05 Student attempt

**Goal:** the professor starts a test-drive and sees, for each question, the student's answer and steps, each with its source linked to the PDF page. Questions with a `none` step show as gaps.

**sys-design:** Stage 2 and 3 (Student agent, Retrieval, Student output), Run order steps 3.1–3.2, Run log (fingerprints), Course store (run inputs, week limit).

## Flow

1. `POST /versions/{id}/test-drives` starts a run (slice 03 job). Requires a reviewed map and confirmed questions. The run config (target version, prerequisite's latest reviewed version or none) is the run log's first line.
2. Per question, in parallel: `gpt-6-luna` student with the topic list (target up to N plus prerequisite), the `lookup_concept` tool (enum of listed IDs, at most 5 calls) and structured output.
3. Re-check: one FTS5 search per `none`/`assumed_knowledge` step (each word quoted). If any hits, one continued student call returns corrected labels.
4. Review screen: questions listed; selecting one shows the question, the student's answer and its steps. Each cited passage shows course, week, file and page, and links to the PDF at that page.

Code questions are skipped.

## Front end

`c2-review`: question list and the student's steps. Add the source link to each citation on the canvas first.

## Acceptance tests

OpenAI is faked.

- The topic list and lookups never include target passages after week N. Prerequisite passages are included whatever their week.
- `lookup_concept` with an unlisted ID is rejected by the schema; a sixth lookup is refused.
- A `none` step with no FTS hits keeps its label and makes no extra call.
- A `none` step with hits triggers exactly one continued call; its relabelled step is stored with evidence.
- A claim with FTS syntax (`n = 2k + 1`) searches without error.
- A question with a `none` step shows as a gap.
- Rerunning with nothing changed makes no API calls. Editing the map reruns every student call.
- Student-facing queries never read the assessment tables (assessment text isn't in any prompt except the question itself).

## Pilot (user runs)

Five questions from one assessment.
