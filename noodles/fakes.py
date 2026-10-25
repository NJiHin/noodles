"""Fake model clients for tests and NOODLES_FAKE=1 (no paid or local model calls)."""
import inspect
import json
import re


class FakeOllama:
    def __init__(self):
        self.calls = 0

    def transcribe(self, png: bytes) -> str:
        self.calls += 1
        return f"[vlm] Transcribed page ({len(png)} bytes of image)."



def _user(messages: list[dict]) -> str:
    return next(m["content"] for m in reversed(messages) if m["role"] == "user")


def fake_extract(messages: list[dict]) -> dict:
    """One topic per passage, named from its first words."""
    out = []
    for pid, text in re.findall(r"^\[(\S+)\] (.*)$", _user(messages), re.M):
        name = " ".join(re.findall(r"[a-z]+", text.lower())[:2]) or pid
        out.append({"name": name, "description": f"Covered in {pid}.", "depth": "explained", "evidence": [pid]})
    return {"concepts": out}


def fake_orchestrate(messages: list[dict]) -> dict:
    """Group weekly records by name; ID from the name, or the previous version's ID for the same name."""
    data = json.loads(_user(messages))
    known = {c["name"]: c["concept_id"] for c in data.get("previous_concepts", [])}
    merged: dict[str, dict] = {}
    for week, records in data["weeks"].items():
        for r in records:
            c = merged.setdefault(r["name"], {"concept_id": known.get(r["name"], f"{data['course']}:{r['name'].replace(' ', '-')}"),
                                              "name": r["name"], "aliases": [], "description": r["description"],
                                              "occurrences": []})
            occ = next((o for o in c["occurrences"] if o["week"] == int(week)), None)
            if occ:
                occ["evidence"] += r["evidence"]
            else:
                c["occurrences"].append({"week": int(week), "depth": r["depth"], "evidence": list(r["evidence"])})
    return {"concepts": list(merged.values())}


def fake_split(messages: list[dict]) -> dict:
    """One short question per line of the paper that ends with '?'."""
    user = _user(messages)
    paper = user.split("ANSWERS:")[0]
    qs = [{"question_id": str(i), "text": t.strip(), "options": None, "type": "short",
           "marking_material": None if "(no answers provided)" in user else f"Model answer {i}."}
          for i, t in enumerate(re.findall(r"([^\n?]+\?)", paper), 1)]
    return {"questions": qs, "unmatched_marking_material": []}


def fake_student(messages: list[dict], tools: list[dict] | None) -> list[dict] | dict:
    """Looks up the first listed topic once, then cites the first passage it got; adds an uncited and an assumed step."""
    outs = [m["output"] for m in messages if m.get("type") == "function_call_output"]
    if tools and not outs:
        ids = tools[0]["parameters"]["properties"]["topic_ids"]["items"]["enum"][:1]
        return [{"type": "function_call", "call_id": "c1", "name": "lookup_concept",
                 "arguments": json.dumps({"topic_ids": ids})}]
    step = lambda claim, source, ev: {"claim": claim, "source": source, "evidence": ev, "reason": None, "accepted_id": None}
    cited = re.findall(r"^\[(\S+)\]", outs[0], re.M)[:1] if outs else []
    steps = [step("The cited passage covers this.", "course", cited)] if cited else []
    assumed = {**step("Integers wrap around on overflow.", "assumed_knowledge", []), "reason": "Covered by the entry requirements."}
    return {"final_answer": "A", "steps": steps + [step("Memoisation caches earlier results.", "none", []), assumed]}


def fake_relabel(messages: list[dict]) -> dict:
    """Every re-checked step becomes a course step citing its first found passage."""
    out = []
    for n, block in re.findall(r"^Step (\d+):(.*?)(?=^Step \d+:|\Z)", _user(messages), re.M | re.S):
        if ids := re.findall(r"^\[(\S+)\]", block, re.M)[:1]:
            out.append({"step": int(n), "source": "course", "evidence": ids, "reason": None, "accepted_id": None})
    return {"steps": out}


class FakeOpenAI:
    """Scripted client: handlers by schema name, each (messages) -> output. Records every call."""

    def __init__(self, **handlers):
        self.handlers = {"WeekRecords": fake_extract, "MergedMap": fake_orchestrate, "QuestionSplit": fake_split,
                         "StudentAnswer": fake_student, "Relabels": fake_relabel,
                         "Grounding": lambda m: {"verdict": "supported", "reason": "The passage states it."},
                         "WebAnswer": lambda m: {"final_answer": "A", "sources": ["https://en.wikipedia.org/wiki/Loop"]},
                         "Mark": lambda m: {"verdict": "correct", "reason": "Matches the marking material."}, **handlers}
        self.calls: list[tuple[str, str, list[dict]]] = []

    def count(self, schema: str) -> int:
        return sum(1 for c in self.calls if c[0] == schema)

    async def complete(self, model, messages, schema, tools=None):
        self.calls.append((schema.__name__, model, list(messages), tools))
        h = self.handlers[schema.__name__]
        out = h(messages, tools) if len(inspect.signature(h).parameters) > 1 else h(messages)
        if inspect.isawaitable(out):
            out = await out
        web = int(any(t.get("type") == "web_search" for t in tools or []))
        return out, {"input_tokens": 100, "cached_tokens": 0, "output_tokens": 20, "web_search_calls": web}
