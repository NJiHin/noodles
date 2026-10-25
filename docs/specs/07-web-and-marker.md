# 07 Web agent and marker

**Goal:** each question also gets a web-search answer, both answers are marked, and the review shows who got it right and the AI exposure. The professor can override any verdict.

**sys-design:** Web agent, Marker, Web agent output, Right and wrong, AI exposure, Run order steps 3.1 and 3.4, Course store (`verdict_overrides`).

## Flow

1. Web agent: `gpt-6-sol` with the Responses API `web_search` tool, run alongside the student. Returns the answer and source URLs. Fingerprint is the question only.
2. Marker: multiple choice and true/false by exact match in code. Other types: one `gpt-6-luna` call per answer with the question, the marking material and that answer only.
3. No marking material: exposure "not assessed".
4. Exposure cell from the sys-design table (only `correct` counts as right).
5. Override: the professor changes a verdict; stored in `verdict_overrides` for the run, and exposure is recomputed.

## Front end

`c2-review`, `c2b-review-exposed`: both answers with verdicts, marker reason, web sources, override.

## Acceptance tests

OpenAI is faked.

- An MCQ answer is marked by exact match with no API call.
- The marker's input contains neither the steps nor which agent answered.
- `partial` counts as wrong in the exposure cell; the review still shows `partial`.
- A question without marking material shows "not assessed".
- Editing course materials reuses the web agent's cached result.
- An override changes the exposure cell and survives a page reload.

## Pilot (user runs)

The same five questions as slice 05. Check web-search cost per question.
