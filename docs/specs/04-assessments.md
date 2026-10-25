# 04 Assessments and questions

**Goal:** the professor uploads each assessment with its answers, states its week cutoff and format, and confirms the question list the system splits out.

**sys-design:** Stage 0 "Assessments into questions", Answer key, Course store (`assessments`, `assessment_files`, `questions`).

## Flow

1. Per assessment: name, `week_cutoff`, `current_format`, the paper file and the answers file. Both go through the slice 01 (and 02) parsing, into `assessment_files`, never `passages`.
2. One `gpt-6-luna` call per assessment splits it into question records (ID, text, options, type, marking material). Each sub-part is its own question.
3. Code checks flag: question text not found verbatim in the parsed paper; a question without marking material; marking material without a question.
4. Question confirm screen: the split with flags shown. The professor edits, deletes or confirms. Code questions are shown as "not assessed (code question)".
5. Confirm writes `questions`.

## Front end (not mocked)

Assessment upload, question confirm.

## Acceptance tests

OpenAI is faked.

- Assessment files never appear in `passages` or in an FTS search.
- A split question whose text isn't in the paper is flagged.
- A question with no marking material, and marking material with no question, are flagged.
- Sub-parts 1a and 1b become two questions.
- Re-uploading identical files makes no API call.
- A question with no marking material can be confirmed and is stored with `marking_material = NULL`.

## Pilot (user runs)

One quiz and one exam from a demo course.
