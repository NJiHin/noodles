"""Page transcription with Qwen3-VL via a local Ollama server (sys-design Stage 0, step 5)."""
import base64
import hashlib
import time
from pathlib import Path

import httpx

MODEL = "qwen3-vl:2b-instruct"  # not the thinking model: better at page parsing and much faster
CACHE_TTL = 30 * 86400  # seconds
PROMPT = (
    "Transcribe this page as markdown. Tables as markdown tables, equations as LaTeX, and describe each "
    "diagram in words. Cover only what is visible on the page; add nothing else."
)


class OllamaError(Exception):
    pass


class Ollama:
    def __init__(self, cache_dir: Path, url: str = "http://127.0.0.1:11434"):
        self.cache_dir, self.url = Path(cache_dir), url
        for old in self.cache_dir.glob("*.md"):  # drop expired pages so the cache doesn't grow forever
            if self._expired(old):
                old.unlink(missing_ok=True)

    @staticmethod
    def _expired(path: Path) -> bool:
        return time.time() - path.stat().st_mtime > CACHE_TTL

    def transcribe(self, png: bytes) -> str:
        """Saved per page as it finishes, so a retry after a failure skips pages already done."""
        key = hashlib.sha256(f"{MODEL}\n{PROMPT}\n".encode() + png).hexdigest()
        path = self.cache_dir / f"{key}.md"
        if path.exists() and not self._expired(path):
            return path.read_text()
        try:
            r = httpx.post(f"{self.url}/api/generate", timeout=600, json={
                "model": MODEL, "prompt": PROMPT, "images": [base64.b64encode(png).decode()],
                "stream": False, "options": {"temperature": 0},
            })
            r.raise_for_status()
            text = r.json()["response"].strip()
        except (httpx.HTTPError, ValueError, KeyError) as e:
            raise OllamaError(f"Ollama is unreachable at {self.url} or failed ({e}). "
                              f"Start Ollama and run `ollama pull {MODEL}`, then confirm again.") from e
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")  # write then rename, so a crash never leaves a half-written page
        tmp.write_text(text)
        tmp.replace(path)
        return text
