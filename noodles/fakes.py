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
    """Group weekly records by name; ID from the name."""
    data = json.loads(_user(messages))
    merged: dict[str, dict] = {}
    for week, records in data["weeks"].items():
        for r in records:
            c = merged.setdefault(r["name"], {"concept_id": f"{data['course']}:{r['name'].replace(' ', '-')}",
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


class FakeOpenAI:
    """Scripted client: handlers by schema name, each (messages) -> output. Records every call."""

    def __init__(self, **handlers):
        self.handlers = {"WeekRecords": fake_extract, "MergedMap": fake_orchestrate, "QuestionSplit": fake_split,
                         **handlers}
        self.calls: list[tuple[str, str, list[dict]]] = []

    def count(self, schema: str) -> int:
        return sum(1 for s, _, _ in self.calls if s == schema)

    async def complete(self, model, messages, schema):
        self.calls.append((schema.__name__, model, messages))
        out = self.handlers[schema.__name__](messages)
        if inspect.isawaitable(out):
            out = await out
        return out, {"input_tokens": 100, "cached_tokens": 0, "output_tokens": 20}
