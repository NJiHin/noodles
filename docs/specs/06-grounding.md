# 06 Grounding checker

**Goal:** every cited step is checked against its passages, and the review shows the verdict. Unsupported citations count as gaps; partial ones show as weak.

**sys-design:** Grounding checker, Grounding checker output, How each source is checked, Gap (code), Run order step 3.3.

## Flow

1. Code check per `course`/`prerequisite` step: every cited ID exists; `course` steps cite target passages up to N; `prerequisite` steps cite prerequisite passages. A failed check is `unsupported` with no LLM call.
2. Otherwise one `gpt-6-luna` call per step sees the claim and its cited passages, and returns `supported` / `partial` / `unsupported` with a reason.
3. Gap rule as in sys-design. The review shows each step's verdict and reason; `partial` reads "Weak citation".

## Front end

`c2-review`: verdict line under each citation.

## Acceptance tests

OpenAI is faked.

- A cited ID that doesn't exist, a `course` step citing a week after N, and a `prerequisite` step citing a target passage are each `unsupported` with no API call.
- An `unsupported` verdict makes the question a gap; `partial` does not.
- Checks for one question's steps run in parallel and are cached per step.
