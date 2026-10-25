# 09 Assumed-knowledge decisions

**Goal:** the professor accepts or rejects each assumption; later runs use those decisions.

**sys-design:** How each source is checked, Professor decisions, Student output ("Decided claims in the prompt"), Course store (`assumed_knowledge`), Stage 4 section 4.

## Flow

1. Review shows each unreviewed `assumed_knowledge` step with the student's reason, and Accept / Reject.
2. A decision is stored per course in `assumed_knowledge`.
3. Next run: the student prompt lists accepted claims (with IDs) and rejected ones. Steps citing an `accepted_id` are skipped in review. Rejected knowledge comes back as `none`, so a gap.
4. After a decision, the UI says the next run reruns the student on every question.

## Front end

`c2c-review-assumption`.

## Acceptance tests

OpenAI is faked.

- Accept and reject are stored per course and survive across versions.
- The student prompt contains decided claims with their IDs.
- A step with an `accepted_id` is not shown for review and is not a gap.
- An `accepted_id` that doesn't exist or was rejected is treated as a new, unreviewed assumption.
- A decision changes every student fingerprint.
