"""Browser smoke check: start the API and Vite on a temp data dir, drive each slice's screens.

Usage: uv run python e2e/smoke.py [--slice N]   (screenshots in /tmp/noodles-smoke/)
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import Page, expect, sync_playwright

sys.path[:0] = [str(Path(__file__).parent.parent), str(Path(__file__).parent.parent / "tests")]
from conftest import make_docx, make_pdf  # noqa: E402

ROOT = Path(__file__).parent.parent
API, WEB = 8799, 5199
SHOTS = Path("/tmp/noodles-smoke")


def wait(url: str, secs: int = 60) -> None:
    end = time.time() + secs
    while time.time() < end:
        try:
            httpx.get(url, timeout=2)
            return
        except httpx.HTTPError:
            time.sleep(0.5)
    raise SystemExit(f"timed out waiting for {url}")


def shot(page: Page, name: str) -> None:
    page.screenshot(path=SHOTS / f"{name}.png", full_page=True)


def slice01(page: Page, tmp: Path) -> dict:
    files = {"Week01_Intro.pdf": make_pdf(["Welcome to CS1010. Variables hold values that a program can change.", "Fig. 1"]),
             "L2-loops.docx": make_docx(["Loops repeat a block of code until a condition becomes false."]),
             "reading.pdf": make_pdf(["Extra reading on recursion"])}
    for n, b in files.items():
        (tmp / n).write_bytes(b)
    page.goto(f"http://127.0.0.1:{WEB}/#/")
    page.get_by_placeholder("CS1010").fill("CS1010")
    page.locator("input[type=file]").set_input_files([str(tmp / n) for n in files])
    expect(page.get_by_label("Week for Week01_Intro.pdf")).to_have_value("1")
    expect(page.get_by_label("Week for L2-loops.docx")).to_have_value("2")
    expect(page.get_by_text("no week in the name")).to_be_visible()
    shot(page, "01-week-confirm")
    page.get_by_label("Week for reading.pdf").fill("2")
    page.get_by_role("button", name="Confirm weeks").click()
    expect(page.get_by_role("heading", name="Materials")).to_be_visible(timeout=120_000)
    expect(page.get_by_text("3 files, 4 pages")).to_be_visible()
    page.get_by_text("L2-loops.docx").click()
    link = page.get_by_role("link", name="Page 1").first
    href = link.get_attribute("href")
    assert href and href.endswith("#page=1"), href
    r = httpx.get(f"http://127.0.0.1:{WEB}{href.split('#')[0]}")
    assert r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code
    shot(page, "01-materials")
    return {"version": page.url.split("/v/")[1].split("/")[0]}


def slice02(page: Page, tmp: Path) -> None:
    """The materials page marks pages transcribed by the (fake) VLM."""
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{STATE['version']}/materials")
    page.get_by_text("Week01_Intro.pdf").click()
    expect(page.get_by_text("vlm", exact=True).first).to_be_visible()
    shot(page, "02-materials-vlm")


SLICES = [slice01, slice02]
STATE: dict = {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", type=int, default=len(SLICES))
    args = ap.parse_args()
    SHOTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = {**os.environ, "NOODLES_DATA": str(tmp / "data"), "NOODLES_RUNS": str(tmp / "runs"), "NOODLES_FAKE": "1",
               "NOODLES_API": f"http://127.0.0.1:{API}"}
        procs = [
            subprocess.Popen(["uv", "run", "uvicorn", "--factory", "noodles.api:from_env", "--port", str(API)],
                             cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=open(tmp / "api.log", "w")),
            subprocess.Popen(["npx", "vite", "--port", str(WEB), "--strictPort", "--host", "127.0.0.1"],
                             cwd=ROOT / "frontend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        ]
        try:
            wait(f"http://127.0.0.1:{API}/courses")
            wait(f"http://127.0.0.1:{WEB}/")
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                for fn in SLICES[: args.slice]:
                    print(f"-- {fn.__name__}")
                    STATE.update(fn(page, tmp) or {})
                    assert not errors, errors
                browser.close()
            print(f"smoke OK, screenshots in {SHOTS}")
        except BaseException:
            print((tmp / "api.log").read_text()[-3000:])
            raise
        finally:
            for pr in procs:
                pr.terminate()


if __name__ == "__main__":
    main()
