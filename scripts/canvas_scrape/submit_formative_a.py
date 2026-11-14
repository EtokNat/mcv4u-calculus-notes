"""Test-submit Formative Check A (assignment 14503, module item 32373) with computed answers.

Strategy:
  1. Login to Canvas as the shared student account.
  2. Navigate to the module item page; click "Load <quiz> in a new window" / "Take the Quiz" / "Resume"
     to open the New Quizzes LTI iframe.
  3. Inside the iframe, wait for Learnosity to render the 8 questions.
  4. Dump the Learnosity item/question structure to disk BEFORE answering, so we can see field IDs.
  5. Fill each question's blanks using the answer map below, submit, read score.

All dumps go to ./submit_fa/. The submission is RECOVERABLE because the quiz has unlimited attempts.
"""
import os, re, json, pathlib, asyncio, time
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"
AID  = 14503       # assignment id for Formative Check A
MID  = 32373       # module item id
OUT  = pathlib.Path(os.environ.get("OUT_ROOT", "./submit_fa")).resolve()
OUT.mkdir(parents=True, exist_ok=True)

# Answers derived from hand-solved Formative_Check_A_Sections_1.1-1.2.md
# Each key is the 1-indexed question number; each value is the ordered list of blank answers
# (or a single value for Numeric questions). We'll fill them positionally into Learnosity's
# text inputs for that question item.
ANSWERS = {
    1: ["3", "37", "61", "5"],
    2: ["3", "-5/3", "-1/3"],
    3: ["-1/3", "-7/13"],
    4: "-5/4",
    5: ["1", "-1", "9", "1/6", "-3/4", "-1/6"],
    6: "-31",
    7: "500",
    8: ["-2", "-1/2", "-1/25"],
}

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def submission_state(page, tag):
    r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/assignments/{AID}/submissions/self")
    status = r.status
    try:
        body = await r.json()
    except Exception:
        body = {"_raw": (await r.text())[:500]}
    (OUT / f"submission_{tag}.json").write_text(json.dumps({"status": status, "body": body}, indent=2, default=str))
    ws = body.get("workflow_state") if isinstance(body, dict) else "?"
    score = body.get("score") if isinstance(body, dict) else "?"
    print(f"  submission[{tag}]: HTTP {status} workflow_state={ws} score={score}", flush=True)
    return body

async def find_quiz_lti_frame(page, deadline_s=30):
    """Wait for the New Quizzes LTI iframe to attach and have content."""
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        for f in page.frames:
            u = f.url or ""
            if "quiz-lti" in u or "quiz-api" in u:
                return f
        await page.wait_for_timeout(500)
    return None

async def dump_quiz_structure(frame, tag):
    """Dump the Learnosity app state (items, questions, response ids)."""
    try:
        state = await frame.evaluate("""() => {
            const out = {};
            try {
                out.has_LearnosityItems = typeof LearnosityItems !== 'undefined';
                out.has_LearnosityApp = typeof LearnosityApp !== 'undefined';
                out.has_LITE = typeof window.LITE !== 'undefined';
                if (typeof LearnosityItems !== 'undefined') {
                    try { out.items = LearnosityItems.getItems(); } catch(e){ out.items_err = String(e); }
                    try { out.questions = LearnosityItems.questionsApp().questions(); } catch(e){ out.q_err = String(e); }
                }
            } catch(e) { out.top_err = String(e); }
            // Fallback: enumerate every input / contenteditable on the page
            out.inputs = Array.from(document.querySelectorAll('input, textarea, [contenteditable]')).map((el, i) => ({
                idx: i, tag: el.tagName, type: el.type || null, name: el.name || null,
                id: el.id || null, cls: el.className || null,
                placeholder: el.placeholder || null,
                aria_label: el.getAttribute('aria-label') || null,
                parent_text: (el.closest('[data-question-index], .lrn_qlabel, .lrn_response')?.innerText || '').slice(0, 200),
            }));
            // Dump every question container's visible text (so we can match prompts)
            out.question_blocks = Array.from(document.querySelectorAll('.lrn_question, [data-question-index], [data-lrn-index]')).map((el,i)=>({
                idx: i, text: (el.innerText||'').slice(0, 500),
                id: el.id || null, attrs: Array.from(el.attributes).map(a=>[a.name,a.value])
            }));
            return out;
        }""")
        (OUT / f"structure_{tag}.json").write_text(json.dumps(state, indent=2, default=str))
        print(f"  structure[{tag}]: inputs={len(state.get('inputs',[]))} blocks={len(state.get('question_blocks',[]))}", flush=True)
        return state
    except Exception as e:
        (OUT / f"structure_{tag}.err").write_text(str(e))
        return None

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 2400})
        page = await ctx.new_page()
        print("Logging in...", flush=True)
        await login(page)
        await submission_state(page, "before")

        # Go to the assignment page; it will auto-launch into the LTI iframe
        print(f"Loading assignment page {AID}...", flush=True)
        await page.goto(f"{BASE}/courses/{CID}/assignments/{AID}?module_item_id={MID}",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)
        await page.screenshot(path=str(OUT / "01_assignment.png"), full_page=True)
        (OUT / "01_assignment.html").write_text(await page.content())

        # Find quiz LTI iframe
        qframe = await find_quiz_lti_frame(page, deadline_s=20)
        if not qframe:
            print("ERROR: quiz LTI frame not found", flush=True)
            await browser.close()
            return
        print(f"  quiz frame: {qframe.url}", flush=True)
        await page.wait_for_timeout(4000)

        # The Learnosity SDK needs a few seconds to render after frame attach
        # Try clicking "Begin" / "Start" if present
        for label in ["Begin", "Start", "Take the Quiz", "Resume Quiz", "Start Quiz"]:
            try:
                btn = qframe.get_by_role("button", name=label, exact=False)
                if await btn.count() > 0:
                    print(f"  clicking button: {label}", flush=True)
                    await btn.first.click(timeout=3000)
                    await page.wait_for_timeout(5000)
                    break
            except Exception:
                continue

        # Dump structure after render
        await dump_quiz_structure(qframe, "01_initial")
        await page.screenshot(path=str(OUT / "02_quiz_loaded.png"), full_page=True)

        # Try to also peek inside any nested Learnosity iframe
        for i, f in enumerate(page.frames):
            print(f"  frame[{i}] name={f.name!r} url={f.url[:120]}", flush=True)

        await browser.close()
        print("Done — review ./submit_fa/structure_01_initial.json to see input layout.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
