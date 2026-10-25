"""Page transcription with Qwen3-VL via a local Ollama server (sys-design Stage 0, step 5)."""
import base64
import hashlib
import re
import time
from pathlib import Path

import httpx

MODEL = "qwen3-vl:2b-instruct"  # not the thinking model: better at page parsing and much faster
CACHE_TTL = 30 * 86400  # seconds
PROMPT = (
    "Transcribe this page as markdown. Tables as markdown tables, equations as LaTeX, and describe each "
    "diagram in words. Cover only what is visible on the page; add nothing else.\n"
    "Rules: output raw markdown, not wrapped in a code block. Never invent URLs or image links. "
    "Never output placeholders such as <!-- Image -->; describe what each image or diagram shows instead. "
    "For charts, give only numbers printed on the chart; do not estimate unlabelled values."
)
# The output cap stops runaway repetition loops in seconds instead of at the 600 s timeout.
OPTIONS = {"temperature": 0, "num_predict": 2048, "repeat_penalty": 1.1}
# Ollama's runner grows by about 400 MB a minute on image requests (measured 3.6 -> 5.6 GB in 5 min on an 8 GB Mac);
# unloading the model frees it. Reloading costs a few seconds against ~30 s per page.
UNLOAD_EVERY = 5  # pages sent to the model
FENCE = re.compile(r"^```(?:markdown)?\s*\n|\n?```\s*$")  # the model wraps pages in a code block despite the prompt


class OllamaError(Exception):
    pass


class Ollama:
    def __init__(self, cache_dir: Path, url: str = "http://127.0.0.1:11434"):
        self.cache_dir, self.url = Path(cache_dir), url
        self.sent = 0  # pages sent to the model, for UNLOAD_EVERY
        for old in self.cache_dir.glob("*.md"):  # drop expired pages so the cache doesn't grow forever
            if self._expired(old):
                old.unlink(missing_ok=True)

    @staticmethod
    def _expired(path: Path) -> bool:
        return time.time() - path.stat().st_mtime > CACHE_TTL

    def transcribe(self, png: bytes) -> str | None:
        """Page markdown, or None if the model ran away (hit the output cap): keep the parser's text then.
        Saved per page as it finishes, so a retry after a failure skips pages already done."""
        key = hashlib.sha256(f"{MODEL}\n{PROMPT}\n{OPTIONS}\n".encode() + png).hexdigest()
        path = self.cache_dir / f"{key}.md"
        if path.exists() and not self._expired(path):
            return path.read_text() or None
        self.sent += 1
        unload = {"keep_alive": 0} if self.sent % UNLOAD_EVERY == 0 else {}  # unloads once this reply is sent
        try:
            r = httpx.post(f"{self.url}/api/generate", timeout=600, json={
                "model": MODEL, "prompt": PROMPT, "images": [base64.b64encode(png).decode()],
                "stream": False, "options": OPTIONS, **unload,
            })
            r.raise_for_status()
            body = r.json()
            text = "" if body.get("done_reason") == "length" else FENCE.sub("", body["response"].strip()).strip()
        except (httpx.HTTPError, ValueError, KeyError) as e:
            raise OllamaError(f"Ollama is unreachable at {self.url} or failed ({e}). "
                              f"Start Ollama and run `ollama pull {MODEL}`, then confirm again.") from e
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")  # write then rename, so a crash never leaves a half-written page
        tmp.write_text(text)
        tmp.replace(path)
        return text or None
