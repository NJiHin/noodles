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


def slice03(page: Page, tmp: Path) -> None:
    """Build the map, edit it (rename, merge, delete, depth, remove evidence), confirm."""
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{STATE['version']}/map")
    page.get_by_role("button", name="Build course map").click()
    expect(page.get_by_text("Draft:")).to_be_visible(timeout=30_000)
    shot(page, "03-map-draft")
    names = page.locator(".topic-name")
    n = names.count()
    assert n >= 3, n
    first_id = page.locator(".topic .id").first.inner_text()
    names.first.fill("renamed topic")
    page.locator(".topic select[aria-label^='Merge']").nth(1).select_option(index=1)
    expect(names).to_have_count(n - 1)
    page.get_by_role("button", name="Delete").last.click()
    expect(names).to_have_count(n - 2)
    page.locator(".occ select").first.select_option("practised")
    page.locator(".ev .chip button").first.click()
    page.get_by_role("button", name="Confirm map").click()
    expect(page.get_by_text("Confirmed:")).to_be_visible()
    expect(page.locator(".topic-name").first).to_have_value("renamed topic")
    m = httpx.get(f"http://127.0.0.1:{API}/versions/{STATE['version']}/map").json()
    assert m["state"] == "reviewed" and len(m["concepts"]) == n - 2, m["state"]
    assert any(c["concept_id"] == first_id and c["name"] == "renamed topic" for c in m["concepts"])
    shot(page, "03-map-confirmed")


def slice04(page: Page, tmp: Path) -> None:
    """Add an assessment with answers, check the split and flags, confirm the questions."""
    (tmp / "quiz.pdf").write_bytes(make_pdf(["Q1. What does a loop repeat in a program written in C?",
                                             "Q2. Why do variables need names in a program written in C?"]))
    (tmp / "quiz-answers.pdf").write_bytes(make_pdf(["1. A block of code, until its condition is false. 2. To refer to values."]))
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{STATE['version']}/assessments")
    page.get_by_label("Name").fill("Week 4 quiz")
    page.get_by_label("Covers weeks 1 to").fill("2")
    page.get_by_label("Current format").select_option("online_quiz")
    page.get_by_label("Paper").set_input_files(str(tmp / "quiz.pdf"))
    page.get_by_label("Answers (optional)").set_input_files(str(tmp / "quiz-answers.pdf"))
    page.get_by_role("button", name="Add").click()
    expect(page.get_by_text("Check and confirm")).to_be_visible(timeout=30_000)
    expect(page.get_by_label("Text of week-4-quiz-q1")).to_have_value("Q1. What does a loop repeat in a program written in C?")
    page.get_by_label("Type of week-4-quiz-q2").select_option("code")
    expect(page.get_by_text("not assessed (code question)")).to_be_visible()
    shot(page, "04-question-confirm")
    page.get_by_role("button", name="Confirm questions").click()
    expect(page.get_by_text("Confirmed, 2 questions")).to_be_visible()
    shot(page, "04-confirmed")
    STATE["assessment"] = "week-4-quiz"


def slice05(page: Page, tmp: Path) -> None:
    """Start a test-drive; the question shows the student's answer, its steps and their PDF source links."""
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{STATE['version']}/review")
    page.get_by_role("button", name="Start test-drive").click()
    expect(page.get_by_role("button", name="Rerun test-drive")).to_be_visible(timeout=30_000)
    expect(page.get_by_text("Not assessed (code question)")).to_be_visible()  # q2 was set to code in slice 04
    page.locator(".item", has_text="What does a loop repeat").click()
    expect(page.get_by_role("heading", name="The student's steps")).to_be_visible()
    expect(page.locator(".ans .v.bad", has_text="Gap")).to_be_visible()  # the fake student adds an uncited step
    expect(page.locator(".why b", has_text="No source.")).to_be_visible()
    link = page.locator(".passage a").first
    expect(link).to_contain_text("CS1010, week")
    href = link.get_attribute("href")
    assert href and "#page=" in href, href
    r = httpx.get(f"http://127.0.0.1:{WEB}{href.split('#')[0]}")
    assert r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code
    shot(page, "05-review")


def slice06(page: Page, tmp: Path) -> None:
    """Each cited step shows its grounding verdict under the citation."""
    expect(page.locator(".s .why", has_text="Supported. The passage states it.").first).to_be_visible()
    shot(page, "06-review-grounding")


def slice07(page: Page, tmp: Path) -> None:
    """Both answers with verdicts and the exposure; an override changes the exposure and survives a reload."""
    expect(page.get_by_role("heading", name="Web-search agent")).to_be_visible()
    expect(page.locator(".rec .facts", has_text="AI-exposed: both answers correct.")).to_be_visible()  # fake marker
    expect(page.get_by_text("en.wikipedia.org")).to_be_visible()
    shot(page, "07-review-answers")
    page.locator(".ans", has_text="Web-search agent").get_by_role("button", name="Override").click()
    page.get_by_label("Override Web-search agent").select_option("incorrect")
    facts = page.locator(".rec .facts", has_text="Student correct, web-search agent incorrect.")
    expect(facts).to_be_visible()
    page.reload()
    expect(facts).to_be_visible()
    expect(page.get_by_text("Overridden by you; the marker said correct.")).to_be_visible()
    shot(page, "07-review-override")


def slice08(page: Page, tmp: Path) -> None:
    """Recommendation block and grouping in the review; summary verdict, actions, grid and bars."""
    expect(page.locator(".rec b", has_text="Fix coverage first, then reassess")).to_be_visible()
    expect(page.get_by_text("Step 2 has no source.")).to_be_visible()
    expect(page.locator(".group", has_text="Fix coverage first")).to_be_visible()
    shot(page, "08-review-recommendation")
    page.get_by_role("link", name="Summary").click()
    expect(page.get_by_text("0 of 1 questions can stay as they are.")).to_be_visible()
    expect(page.locator(".actions b", has_text="Fix coverage first")).to_be_visible()
    expect(page.locator(".cell.good .chip", has_text="Q1")).to_be_visible()  # overridden in slice 07: web wrong
    expect(page.locator(".bar span.gap")).to_have_count(1)
    shot(page, "08-summary")
    page.locator(".actions .chip").first.click()
    expect(page.get_by_role("heading", name="The student's steps")).to_be_visible()


def slice09(page: Page, tmp: Path) -> None:
    """An unreviewed assumption is listed for review; rejecting it makes it a gap and says the next run reruns."""
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{STATE['version']}/summary")
    expect(page.locator(".actions b", has_text="Confirm 1 assumption")).to_be_visible()
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{STATE['version']}/review")
    item = page.locator(".item", has_text="Assumes: Integers wrap around on overflow.")
    expect(item).to_be_visible()
    item.click()
    expect(page.get_by_text("Student's reason: Covered by the entry requirements.")).to_be_visible()
    shot(page, "09-review-assumption")
    page.get_by_role("button", name="Reject, count as a gap").click()
    expect(page.get_by_text("Rejected: counts as a gap.")).to_be_visible()
    expect(page.get_by_text("reruns the student on every question")).to_be_visible()
    expect(item).to_have_count(0)
    shot(page, "09-review-rejected")


def slice10(page: Page, tmp: Path) -> None:
    """Topics by week with depth cells, the question using a topic, never-assessed topics, the gap list."""
    page.get_by_role("link", name="Learning path").click()
    expect(page.get_by_role("heading", name="Topics by week")).to_be_visible()
    expect(page.locator(".lp .c .d").first).to_be_visible()
    expect(page.locator(".lp .by .chip", has_text="Q1").first).to_be_visible()
    expect(page.get_by_role("heading", name="Coverage gaps")).to_be_visible()
    shot(page, "10-learning-path")


SLICES = [slice01, slice02, slice03, slice04, slice05, slice06, slice07, slice08, slice09, slice10]
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
