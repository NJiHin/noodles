"""Stage 4 in code: lookup or reasoning, recommendation rules, summary (sys-design "Recommendation rules")."""

FORMAT_LABEL = {"take_home": "take-home", "online_quiz": "online quiz", "invigilated_exam": "invigilated exam"}
ADD_A_CHECK = "Or, if it must stay open, add a check: oral defence, staged submissions or an in-class component."
OPEN_FORMATS = ("take_home", "online_quiz")  # not invigilated

# key -> (group in the review, title, advisory text, current formats it matches)
RULES = {
    "fix_coverage": ("Fix coverage first", "Fix coverage first, then reassess",
                     "A step has no source, a citation the grounding checker rejected, or knowledge you rejected.", ()),
    "not_assessed": ("AI exposure not assessed", "AI exposure not assessed",
                     "There is no marking material, so there is no format recommendation.", ()),
    "review_untaught": ("Review the question", "Review: needs knowledge that's neither taught nor declared",
                        "The web-search agent answers it correctly; the course-limited student doesn't.", ()),
    "review_broken": ("Review the question", "Review: the question may be broken",
                      "Neither the course-limited student nor the web-search agent answers it correctly.", ()),
    "keep_open": ("Could be open or take-home", "Keep it open or take-home",
                  "Only the course-limited student answers it correctly: it already certifies learning.", OPEN_FORMATS),
    "closed_book": ("Change format", "Closed-book, invigilated",
                    "If AI use isn't intended, consider a closed-book, invigilated setting. " + ADD_A_CHECK,
                    ("invigilated_exam",)),
    "open_book_or_redesign": ("Change format", "Open-book invigilated, or redesign",
                              "If AI use isn't intended, consider an open-book invigilated setting, or redesign it "
                              "to use course-specific material. " + ADD_A_CHECK, ("invigilated_exam",)),
}
CODE = {"key": "code", "group": "Not assessed (code question)", "title": "Not assessed (code question)",
        "text": "Code questions aren't run in this version.", "facts": ""}
# top actions, in the order the rules apply
ACTIONS = [("fix_coverage", ["fix_coverage"]), ("review", ["review_untaught", "review_broken"]),
           ("keep_open", ["keep_open"]), ("change_format", ["closed_book", "open_book_or_redesign"])]


def is_lookup(q: dict) -> bool:
    """One knowledge step or fewer is lookup; two or more is reasoning (a heuristic)."""
    return len(q["answer"]["steps"]) <= 1


def recommend(q: dict) -> dict:
    """First matching rule. q: type, current_format, gap, marks (effective verdicts or None), answer (steps)."""
    if q["type"] == "code":
        return CODE
    m = q["marks"]
    right = m and {k: v["verdict"] == "correct" for k, v in m.items()}
    if q["gap"]:
        key = "fix_coverage"
    elif not m:
        key = "not_assessed"
    elif not right["student"]:
        key = "review_untaught" if right["web"] else "review_broken"
    elif not right["web"]:
        key = "keep_open"
    else:
        key = "closed_book" if is_lookup(q) else "open_book_or_redesign"
    group, title, text, matches = RULES[key]
    if key == "fix_coverage" and (why := [
            f"step {i} has no source" if s["source"] == "none" else
            f"step {i} relies on knowledge you rejected" if (s.get("assumption") or {}).get("state") == "rejected" else
            f"step {i}'s citation was rejected by the grounding checker"
            for i, s in enumerate(q["answer"]["steps"], 1)
            if s["source"] == "none" or (s.get("grounding") or {}).get("verdict") == "unsupported"
            or (s.get("assumption") or {}).get("state") == "rejected"]):
        text = "; ".join(why).capitalize() + "."
    n = len(q["answer"]["steps"])
    facts = []
    if m:
        facts.append("AI-exposed: both answers correct." if right["student"] and right["web"] else
                     f"Student {m['student']['verdict']}, web-search agent {m['web']['verdict']}.")
    facts.append(f"{'Lookup' if is_lookup(q) else 'Reasoning'}: {n} knowledge step{'s' * (n != 1)}.")
    facts.append(f"Current format: {FORMAT_LABEL[q['current_format']]}.")
    if q["current_format"] in matches:
        group = "Keep as is"
        text = f"Recommended: {title[0].lower() + title[1:]}. This matches the current format, {FORMAT_LABEL[q['current_format']]}."
        title = "Keep as is"
    return {"key": key, "group": group, "title": title, "text": text, "facts": " ".join(facts)}


def summary(questions: list[dict]) -> dict:
    """Key figures, top actions, exposure grid and per-assessment bars from the review's questions."""
    done = [q for q in questions if q["answer"] and q["type"] != "code"]
    by_key = lambda keys: [q["question_id"] for q in done if q["recommendation"]["key"] in keys
                           and q["recommendation"]["group"] != "Keep as is"]
    groups = {}
    for q in done:
        groups.setdefault(q["recommendation"]["group"], 0)
        groups[q["recommendation"]["group"]] += 1
    unreviewed = [(q["question_id"], s["step_id"]) for q in done for s in q["answer"]["steps"]
                  if (s.get("assumption") or {}).get("state") == "unreviewed"]
    order = [q["question_id"] for q in done]
    assessments: dict[str, dict] = {}
    for q in done:
        a = assessments.setdefault(q["assessment_id"], {"assessment_id": q["assessment_id"], "week_cutoff": q["week_cutoff"],
                                                       "current_format": q["current_format"], "segments": [], "groups": {}})
        a["segments"].append("gap" if q["gap"] else {"ai_exposed": "ai", "course_specific": "ok"}.get(q["exposure"], "other"))
        g = q["recommendation"]["group"]
        a["groups"][g] = a["groups"].get(g, 0) + 1
    return {
        "assessed": len(done), "keep": groups.get("Keep as is", 0), "groups": groups,
        "figures": {"gaps": sum(q["gap"] for q in done), "ai_exposed": sum(q["exposure"] == "ai_exposed" for q in done),
                    "assumptions": len(unreviewed)},
        "actions": [{"key": k, "questions": ids} for k, keys in ACTIONS if (ids := by_key(keys))]
        + ([{"key": "confirm_assumptions", "questions": sorted({q for q, _ in unreviewed}, key=order.index)}] if unreviewed else []),
        "matrix": {cell: [q["question_id"] for q in done if q["exposure"] == cell]
                   for cell in ("ai_exposed", "course_specific", "neither_taught", "broken_or_gap")},
        "assessments": list(assessments.values()),
    }
