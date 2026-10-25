# 11 Versions and changes

**Goal:** the professor re-uploads an edited course, pays only for what changed, keeps stable topic IDs, and sees what changed since the last run.

**sys-design:** Course-level versioning, Stage 1 step 3 and Updates, Run log, Stage 4 section 5.

## Flow

1. Re-upload or week correction creates a new version under the same course code (slice 01).
2. The orchestrator gets the previous reviewed version's concepts as a merge reference. Map review lists IDs that disappeared and IDs that are new.
3. A test-drive on the new version reuses cached results wherever a call's inputs are unchanged.
4. Changes page: this run against the latest run of the previous version, matched by `question_id` and `concept_id`. Counts per kind of change at the top, each entry linked; before → after markers on changed items in the review and learning path. First version: "no previous run".

## Front end

`c5-changes`; ID diff on the map review screen (slice 03).

## Acceptance tests

OpenAI is faked.

- Editing a week-4 passage reruns only student calls for questions with `week_cutoff` ≥ 4.
- The orchestrator prompt contains the previous version's concepts; on a course's first version it contains none.
- Map review lists a renamed topic as one disappeared and one new ID.
- A changed verdict, gap or recommendation appears in the changes list with before and after.
- A question whose text changed is marked "question edited".
- A depth change in one week appears under course map changes.
