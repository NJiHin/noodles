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
    # Hold the confirm request and fake one progress reading, so the progress state can be seen.
    held = []
    page.route("**/courses/CS1010/versions", lambda route: held.append(route))
    page.route("**/progress", lambda route: route.fulfill(json={
        "Week01_Intro.pdf": {"done": 1, "total": 2}, "L2-loops.docx": {"done": 0, "total": 0}, "reading.pdf": {"done": 0, "total": 1}}))
    page.get_by_role("button", name="Confirm weeks").click()
    expect(page.get_by_role("row", name="Week01_Intro.pdf")).to_contain_text("1/2")
    expect(page.get_by_role("row", name="reading.pdf")).to_contain_text("0/1")
    shot(page, "01-reading-progress")
    held[0].continue_()
    page.unroute("**/progress")
    page.unroute("**/courses/CS1010/versions")
    expect(page.get_by_role("heading", name="Materials")).to_be_visible(timeout=120_000)
    expect(page.get_by_text("3 files, 4 pages")).to_be_visible()
    page.get_by_text("L2-loops.docx").click()
    page.get_by_role("button", name="Page 1").click()
    link = page.get_by_role("link", name="Open PDF")
    href = link.get_attribute("href")
    assert href and href.endswith("#page=1"), href
    r = httpx.get(f"http://127.0.0.1:{WEB}{href.split('#')[0]}")
    assert r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code
    page.get_by_role("button", name="Close").click()
    shot(page, "01-materials")
    return {"version": page.url.split("/v/")[1].split("/")[0]}


def slice02(page: Page, tmp: Path) -> None:
    """The materials page marks pages transcribed by the (fake) VLM."""
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{STATE['version']}/materials")
    page.get_by_text("Week01_Intro.pdf").click()
    expect(page.get_by_text("vlm", exact=True).first).to_be_visible()
    shot(page, "02-materials-vlm")
    # The page viewer: transcription next to the page image, editable.
    page.get_by_role("button", name="Page 2").click()
    img = page.get_by_role("img", name="Page 2 of Week01_Intro.pdf")
    expect(img).to_be_visible()
    page.wait_for_function("() => { const i = document.querySelector('.viewer-img img'); return i.complete && i.naturalWidth > 0 }")
    shot(page, "02-viewer")
    page.get_by_role("button", name="Edit").click()
    # keeps the first words, so the fake map extractor names the same topics for later slices
    page.get_by_label("Transcription").fill("[vlm] Transcribed page, corrected by hand.")
    shot(page, "02-viewer-edit")
    page.get_by_role("button", name="Save").click()
    expect(page.locator(".viewer-text")).to_contain_text("[vlm] Transcribed page, corrected by hand.")
    page.get_by_role("button", name="Close").click()
    expect(page.get_by_role("button", name="Page 2")).to_contain_text("[vlm] Transcribed page, corrected by hand.")
    files = httpx.get(f"http://127.0.0.1:{API}/versions/{STATE['version']}/files").json()["files"]
    assert any(p["text"] == "[vlm] Transcribed page, corrected by hand." for f in files for p in f["pages"])


def slice03(page: Page, tmp: Path) -> None:
    """Build the map, edit it (rename, merge, delete, depth, remove evidence), confirm."""
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{STATE['version']}/map")
    page.get_by_role("button", name="Build course map").click()
    expect(page.get_by_text("Draft:")).to_be_visible(timeout=30_000)
    shot(page, "03-map-draft")
    rows = page.locator(".mx-body .mx-row")
    n = rows.count()
    assert n >= 3, n
    closed = page.locator(".mx-band:not(.open)")
    while closed.count():  # open every week group
        closed.first.click()
    rows.first.click()  # ↓ walks to the next topic, Esc closes the editor
    expect(page.locator(".ed-head b")).to_have_text(rows.first.locator(".nm").inner_text())
    page.keyboard.press("ArrowDown")
    expect(page.locator(".ed-head b")).to_have_text(rows.nth(1).locator(".nm").inner_text())
    page.keyboard.press("Escape")
    expect(page.locator(".cm-hint")).to_be_visible()
    rows.nth(1).click()
    expect(page.locator(".cm-ed")).to_be_visible()
    page.locator(".cm-ed select[aria-label^='Merge']").select_option(index=1)
    expect(rows).to_have_count(n - 1)
    rows.last.click()
    page.get_by_role("button", name="Delete topic").click()
    expect(rows).to_have_count(n - 2)
    expect(page.locator(".cm-hint")).to_be_visible()
    page.locator(".mx-body .mx-row .c").first.click()  # a week's cell opens the editor at that week
    expect(page.locator(".ed-wk.flash")).to_be_visible()
    first_id = page.locator(".ed-id").inner_text()
    page.locator(".cm-ed .topic-name").fill("renamed topic")
    page.locator(".cm-ed .ev .chip a").first.click()  # evidence opens the page viewer, as on Materials
    expect(page.locator("dialog.viewer .viewer-img img")).to_be_visible()
    shot(page, "03-map-evidence-viewer")
    page.locator("dialog.viewer").get_by_role("button", name="Close").click()
    expect(page.locator("dialog.viewer")).to_have_count(0)
    page.locator(".cm-ed .ed-wk select").first.select_option("practised")
    page.locator(".cm-ed .ev .chip button").first.click()
    shot(page, "03-map-editing")
    expect(page.get_by_role("button", name="Confirm map")).to_contain_text("change")
    page.get_by_role("button", name="Confirm map").click()
    expect(page.get_by_text("Confirmed:")).to_be_visible()
    expect(page.locator(".mx-body .nm", has_text="renamed topic")).to_have_count(1)
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
    link.click()
    expect(page.locator("dialog.viewer .viewer-img img")).to_be_visible()
    page.get_by_role("button", name="Close").click()


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
    """Recommendation block and grouping in the review; summary verdict, actions and grid."""
    expect(page.locator(".rec b", has_text="Fix coverage first, then reassess")).to_be_visible()
    expect(page.get_by_text("Step 2 has no source.")).to_be_visible()
    expect(page.locator(".group", has_text="Fix coverage first")).to_be_visible()
    shot(page, "08-review-recommendation")
    page.get_by_role("link", name="Summary").click()
    expect(page.get_by_text("0 of 1 questions can stay as they are.")).to_be_visible()
    expect(page.locator(".actions b", has_text="Fix coverage first")).to_be_visible()
    expect(page.locator(".cell.good .chip", has_text="Q1")).to_be_visible()  # overridden in slice 07: web wrong
    expect(page.get_by_role("heading", name="By assessment")).to_have_count(0)  # repeated the actions and the grid
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
    """Summary: what the assessments cover (topics per week, assessed or never), and the never-assessed figure."""
    page.get_by_role("link", name="Summary").click()
    expect(page.get_by_role("heading", name="What the assessments cover")).to_be_visible()
    expect(page.locator(".cov-col").first).to_be_visible()
    expect(page.locator(".figures")).to_contain_text("never assessed")
    expect(page.locator(".cov-per > div").first).to_contain_text("never assessed")
    expect(page.get_by_role("link", name="Learning path")).to_have_count(0)
    shot(page, "10-summary-coverage")


def api_wait(run_id: str) -> None:
    end = time.time() + 30
    while httpx.get(f"http://127.0.0.1:{API}/runs/{run_id}").json()["status"] == "running":
        assert time.time() < end, run_id
        time.sleep(0.2)


def slice11(page: Page, tmp: Path) -> None:
    """A re-upload with one file edited: map ID diff, then the changes page and markers after a new test-drive."""
    a = f"http://127.0.0.1:{API}"
    files = {"Week01_Intro.pdf": make_pdf(["Welcome to CS1010. Variables hold values that a program can change.", "Fig. 1"]),
             "L2-loops.docx": make_docx(["Loops repeat a block of code until a condition becomes false."]),
             "reading.pdf": make_pdf(["Further reading on sorting"])}
    up = httpx.post(f"{a}/courses/CS1010/uploads", files=[("files", (n, b)) for n, b in files.items()]).json()
    v2 = httpx.post(f"{a}/courses/CS1010/versions", timeout=120,
                    json={"upload_id": up["upload_id"], "weeks": {"Week01_Intro.pdf": 1, "L2-loops.docx": 2, "reading.pdf": 2}}).json()["version_id"]
    api_wait(httpx.post(f"{a}/versions/{v2}/map-runs").json()["run_id"])
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{v2}/map")
    expect(page.get_by_role("heading", name="Topic IDs since the previous version")).to_be_visible()
    shot(page, "11-map-id-diff")
    expect(page.locator(".id-diff .chip", has_text="CS1010:loops-repeat")).to_be_visible()
    shot(page, "11-map-id-diff")
    page.get_by_role("button", name="Confirm map").click()
    expect(page.get_by_text("Confirmed:")).to_be_visible()
    r = httpx.post(f"{a}/versions/{v2}/assessments", data={"name": "Week 4 quiz", "week_cutoff": 2, "current_format": "online_quiz"},
                   files={"paper": ("quiz.pdf", (tmp / "quiz.pdf").read_bytes()),
                          "answers": ("quiz-answers.pdf", (tmp / "quiz-answers.pdf").read_bytes())}, timeout=120).json()
    api_wait(r["run_id"])
    qs = httpx.get(f"{a}/versions/{v2}/assessments").json()[0]["questions"]
    httpx.put(f"{a}/versions/{v2}/assessments/week-4-quiz/questions", json={"questions": [
        {k: q[k] for k in ("question_id", "text", "options", "type", "marking_material")} for q in qs]}).raise_for_status()
    api_wait(httpx.post(f"{a}/versions/{v2}/test-drives", json={"prerequisite": None}).json()["run_id"])
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{v2}/changes")
    expect(page.get_by_role("heading", name="Changes since last run")).to_be_visible()
    expect(page.get_by_text("with changed results")).to_be_visible()
    expect(page.locator(".oc a.q", has_text="Q1")).to_be_visible()  # the web override was on the previous run only
    shot(page, "11-changes")
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{v2}/review")
    expect(page.locator(".item .chg").first).to_be_visible()
    page.goto(f"http://127.0.0.1:{WEB}/#/v/{STATE['version']}/changes")
    expect(page.get_by_text("There is no previous run to compare with")).to_be_visible()


def slice12(page: Page, tmp: Path) -> None:
    """Method steps, this run's facts (prices unset under the fake: token counts instead of dollars), limitations."""
    page.get_by_role("link", name="Method and limitations").click()
    expect(page.get_by_role("heading", name="How it works")).to_be_visible()
    expect(page.get_by_text("Rerun this time")).to_be_visible()
    expect(page.get_by_text("Prices not set")).to_be_visible()
    expect(page.get_by_text("One attempt per question.")).to_be_visible()
    shot(page, "12-method")


def slice13(page: Page, tmp: Path) -> None:
    """Add files to the course's latest version: one new, one replacing; notices on materials, map and results."""
    a = f"http://127.0.0.1:{API}"
    vid = next(c for c in httpx.get(f"{a}/courses").json() if c["code"] == "CS1010")["versions"][0]["id"]
    replaced = httpx.get(f"{a}/versions/{vid}/files").json()["files"][0]["filename"]
    (tmp / "add").mkdir()
    (tmp / "add" / "Week03_Recursion.pdf").write_bytes(make_pdf(["Recursion solves a problem by calling itself on smaller input."]))
    (tmp / "add" / replaced).write_bytes(make_pdf(["Revised notes: variables hold values a program can change."]))
    page.goto(f"http://127.0.0.1:{WEB}/#/")
    with page.expect_file_chooser() as fc:
        page.locator("li", has_text=vid).get_by_role("button", name="Add files").click()
    fc.value.set_files([tmp / "add" / "Week03_Recursion.pdf", tmp / "add" / replaced])
    expect(page.get_by_role("heading", name="Add files to CS1010")).to_be_visible()
    expect(page.locator(".t .rep")).to_contain_text(f"replaces {replaced}")
    shot(page, "13-home-add-files")
    page.get_by_role("button", name="Add to course").click()
    expect(page.get_by_role("heading", name="Materials")).to_be_visible(timeout=30_000)
    assert vid in page.url
    expect(page.locator(".notice.info")).to_contain_text("Week03_Recursion.pdf")
    page.get_by_role("link", name="Course map").click()
    expect(page.locator(".notice.warn")).to_contain_text("after this map was built")
    shot(page, "13-map-outdated")
    page.get_by_role("link", name="Summary").click()
    expect(page.locator(".notice.warn")).to_contain_text("Rebuild and confirm the course map first")
    shot(page, "13-summary-outdated")


SLICES = [slice01, slice02, slice03, slice04, slice05, slice06, slice07, slice08, slice09, slice10, slice11, slice12, slice13]
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
