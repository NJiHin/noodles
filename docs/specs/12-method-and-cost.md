# 12 Method, limitations and cost

**Goal:** the report explains how it was produced, its limits, and what the run actually cost.

**sys-design:** Stage 4 section 6, Run log (cost reporting), Single run per agent, Implementation (models).

## Flow

1. Run facts from the run log and course store: version and comparison run, prerequisite, passage and transcribed counts, topics and when confirmed, questions, how many reran, models.
2. Actual cost: token usage per call type priced per model, plus web-search calls. Cached results add nothing.
3. Fixed text for the method steps and the limitations listed in sys-design.

## Front end

`c6-method`.

## Acceptance tests

- Cost is the sum over the run's new records; a fully cached rerun costs 0.
- Web-search calls are counted and priced separately.
- "Rerun this time" counts questions with at least one new call.
