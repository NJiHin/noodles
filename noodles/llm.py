"""LLM call wrapper and run log (sys-design "Run log", "Implementation").

Every call is fingerprinted (the content it sees, prompt version, model). A record with the same
fingerprint in any run log under the course code is reused; otherwise the client is called with
retries under a concurrency limit. Each call (new or cached) is appended to the run's JSONL as it finishes.
"""
import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

LUNA, SOL = "gpt-6-luna", "gpt-6-sol"


class LLMError(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


class OpenAIClient:
    """Thin adapter over the OpenAI Responses API with strict JSON-schema output."""

    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(max_retries=0)  # retries are ours, so each failure is visible

    async def complete(self, model: str, messages: list[dict], schema: type[BaseModel],
                       tools: list[dict] | None = None) -> tuple[Any, dict]:
        """Returns (output, usage): a list of function_call items if the model called a tool, else the parsed JSON."""
        from openai.lib._pydantic import to_strict_json_schema
        r = await self.client.responses.create(
            model=model, input=messages, temperature=0, reasoning={"effort": "none"}, **({"tools": tools} if tools else {}),
            text={"format": {"type": "json_schema", "name": schema.__name__, "strict": True,
                             "schema": to_strict_json_schema(schema)}})
        u = r.usage
        usage = {"input_tokens": u.input_tokens, "cached_tokens": u.input_tokens_details.cached_tokens,
                 "output_tokens": u.output_tokens, "web_search_calls": sum(o.type == "web_search_call" for o in r.output)}
        if calls := [{"type": "function_call", "call_id": o.call_id, "name": o.name, "arguments": o.arguments}
                     for o in r.output if o.type == "function_call"]:
            return calls, usage
        try:
            return json.loads(r.output_text), usage
        except ValueError:
            return r.output_text, usage


def load_cache(runs_dir: Path, code: str) -> dict[str, dict]:
    """Every call record under the course code, by fingerprint."""
    cache: dict[str, dict] = {}
    for path in sorted((runs_dir / code).glob("*/*.jsonl")):
        for line in path.read_text().splitlines():
            rec = json.loads(line)
            if rec.get("type") == "call":
                cache.setdefault(rec["fingerprint"], rec)
    return cache


def find_log(runs_dir: Path, run_id: str) -> Path | None:
    return next(runs_dir.glob(f"*/*/{run_id}.jsonl"), None)


def read_log(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


class Run:
    """One run: its JSONL log, the course's cache and a client. Create with Run.start()."""

    def __init__(self, path: Path, client, cache: dict, semaphore: asyncio.Semaphore, retries: int, retry_delay: float):
        self.path, self.client, self.cache = path, client, cache
        self.id = path.stem
        self.semaphore, self.retries, self.retry_delay = semaphore, retries, retry_delay
        self.inflight: dict[str, asyncio.Future] = {}  # identical calls running at once share one request

    @classmethod
    def start(cls, runs_dir: Path, code: str, version: str, config: dict, client, *,
              concurrency: int = 4, retries: int = 3, retry_delay: float = 2.0) -> "Run":
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "-" + uuid.uuid4().hex[:6]  # sorts in start order
        path = runs_dir / code / version / f"{run_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        cache = load_cache(runs_dir, code)
        run = cls(path, client, cache, asyncio.Semaphore(concurrency), retries, retry_delay)
        run.write({"type": "config", "run_id": run_id, "course": code, "version": version, "started_at": now(), **config})
        return run

    def write(self, record: dict) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(record) + "\n")

    def end(self, error: str | None = None) -> None:
        self.write({"type": "end", "status": "failed" if error else "done", "error": error, "ended_at": now()})

    async def cached(self, call_type: str, model: str, prompt_version: str, sees: Any, question_id: str | None,
                     produce) -> dict:
        """Reuse the record with the same fingerprint, else `await produce()` -> (output, usage, extra fields)
        and log it. Returns the record. For calls made of several requests (the student's tool loop)."""
        fp = fingerprint(prompt_version, model, sees)
        if fp in self.inflight:
            await asyncio.shield(self.inflight[fp])
        hit = self.cache.get(fp)
        if hit:
            self.write({**hit, "question_id": question_id, "cached": True, "at": now()})
            return hit
        self.inflight[fp] = done = asyncio.get_running_loop().create_future()
        try:
            output, usage, extra = await produce()
            rec = {"type": "call", "fingerprint": fp, "call_type": call_type, "model": model, "question_id": question_id,
                   "usage": usage, "output": output, **extra, "cached": False, "at": now()}
            self.cache[fp] = rec
            self.write(rec)
            return rec
        finally:
            del self.inflight[fp]
            done.set_result(None)  # waiters then find the record in the cache, or call themselves if it failed

    async def request(self, call_type: str, model: str, messages: list[dict], schema: type[BaseModel],
                      tools: list[dict] | None = None) -> tuple[Any, dict]:
        """One API request with retries under the concurrency limit, not cached.
        Returns (output, usage): a list of tool calls, or the validated schema instance."""
        error = None
        for attempt in range(self.retries):
            if attempt:
                await asyncio.sleep(self.retry_delay * 2 ** (attempt - 1))
            try:
                async with self.semaphore:
                    raw, usage = await self.client.complete(model, messages, schema, tools)
                return (raw if isinstance(raw, list) else schema.model_validate(raw)), usage
            except ValidationError as e:
                error = f"{call_type} output failed its schema: {e.errors()[0]['msg']}"
            except Exception as e:  # API or network failure: retry
                error = f"{call_type} call failed: {e}"
        raise LLMError(f"{error} (after {self.retries} attempts)")

    async def call(self, call_type: str, model: str, prompt_version: str, messages: list[dict],
                   schema: type[BaseModel], question_id: str | None = None, sees: Any = None,
                   tools: list[dict] | None = None) -> BaseModel:
        """Structured call. `sees` is the content the call can see (defaults to the messages).
        `tools` here are hosted tools (web_search) that end in a structured answer."""
        async def produce():
            out, usage = await self.request(call_type, model, messages, schema, tools)
            return out.model_dump(), usage, {}
        rec = await self.cached(call_type, model, prompt_version, messages if sees is None else sees, question_id, produce)
        return schema.model_validate(rec["output"])


def add_usage(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0) + b.get(k, 0) for k in {*a, *b}}
