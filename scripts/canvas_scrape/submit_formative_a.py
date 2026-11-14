"""Test-submit Formative Check A (assignment 14503, module item 32373).

Phase 1 (this version): PROBE ONLY. Go directly to the LTI launch URL, wait for the quiz LTI
page to render, dump every iframe and the Learnosity input layout to disk. We do NOT submit
until we understand the field structure.

Phase 2 (later): fill blanks + submit once the field map is clear.
"""
import os, re, json, pathlib, asyncio, time
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"
AID  = 14503
MID  = 32373
OUT  = pathlib.Path(os.environ.get("OUT_ROOT", "./submit_fa")).resolve()
OUT.mkdir(parents=True, exist_ok=True)

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

async def dump_frame_tree(page, tag):
    """List every frame, URL, name, and the first 300 chars of its visible body."""
    rows = []
    for i, f in enumerate(page.frames):
        row = {"idx": i, "name": f.name, "url": (f.url or "")[:200]}
        try:
            row["body_preview"] = (await f.locator("body").inner_text(timeout=2000))[:400]
        except Exception as e:
            row["body_err"] = str(e)[:200]
        rows.append(row)
    (OUT / f"frames_{tag}.json").write_text(json.dumps(rows, indent=2, default=str))
    print(f"  frames[{tag}]: {len(rows)} total", flush=True)
    for r in rows:
        print(f"    [{r['idx']}] {r['url'][:100]}", flush=True)
    return rows

async def dump_learnosity_structure(frame, tag):
    """From inside a Learnosity frame, snapshot every input/question container."""
    try:
        state = await frame.evaluate("""() => {
            const out = {inputs:[], blocks:[], globals:{}};
            try {
                out.globals.has_LearnosityItems = typeof LearnosityItems !== 'undefined';
                out.globals.has_LearnosityApp = typeof LearnosityApp !== 'undefined';
                if (typeof LearnosityItems !== 'undefined') {
                    try { out.learnosity_items = LearnosityItems.getItems && LearnosityItems.getItems(); } catch(e){ out.li_err = String(e); }
                    try { out.learnosity_questions = LearnosityItems.questionsApp && LearnosityItems.questionsApp().questions(); } catch(e){ out.lq_err = String(e); }
                }
            } catch(e) { out.top_err = String(e); }
            out.inputs = Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"]')).map((el,i)=>({
                idx: i, tag: el.tagName, type: el.type || null,
                name: el.name || null, id: el.id || null,
                cls: (el.className||'').slice(0,200),
                placeholder: el.placeholder || null,
                aria_label: el.getAttribute('aria-label') || null,
                data_lrn: el.getAttribute('data-lrn-response-id') || el.getAttribute('data-response-id') || null,
                parent_question_text: (el.closest('.lrn_question, [data-question-index]')?.innerText || '').slice(0, 300),
            }));
            out.blocks = Array.from(document.querySelectorAll('.lrn_question, .lrn_response, [data-question-index]')).map((el,i)=>({
                idx: i, id: el.id || null,
                class: (el.className||'').slice(0,200),
                text: (el.innerText||'').slice(0,500),
            }));
            return out;
        }""")
        (OUT / f"learnosity_{tag}.json").write_text(json.dumps(state, indent=2, default=str))
        print(f"  learnosity[{tag}]: inputs={len(state.get('inputs',[]))} blocks={len(state.get('blocks',[]))}", flush=True)
        return state
    except Exception as e:
        (OUT / f"learnosity_{tag}.err").write_text(str(e))
        return None

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 2400})
        page = await ctx.new_page()
        print("Logging in...", flush=True)
        await login(page)
        await submission_state(page, "before")

        # Direct LTI launch
        launch_url = f"{BASE}/courses/{CID}/assignments/{AID}/launch"
        print(f"Launching LTI: {launch_url}", flush=True)
        try:
            await page.goto(launch_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  launch goto err: {e}", flush=True)
        await page.wait_for_timeout(8000)
        print(f"  landed URL: {page.url}", flush=True)
        (OUT / "01_after_launch.html").write_text(await page.content())
        await page.screenshot(path=str(OUT / "01_after_launch.png"), full_page=True)
        await dump_frame_tree(page, "01_after_launch")

        # Wait longer for Learnosity to boot
        await page.wait_for_timeout(10000)
        (OUT / "02_after_wait.html").write_text(await page.content())
        await page.screenshot(path=str(OUT / "02_after_wait.png"), full_page=True)
        await dump_frame_tree(page, "02_after_wait")

        # Also try the module item wrapper URL in case launch URL alone doesn't trigger
        print("\nTrying module-item URL...", flush=True)
        try:
            await page.goto(f"{BASE}/courses/{CID}/modules/items/{MID}", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(8000)
            print(f"  landed URL: {page.url}", flush=True)
            (OUT / "03_module_item.html").write_text(await page.content())
            await page.screenshot(path=str(OUT / "03_module_item.png"), full_page=True)
            await dump_frame_tree(page, "03_module_item")
            await page.wait_for_timeout(8000)
            await dump_frame_tree(page, "03b_after_wait")
            await page.screenshot(path=str(OUT / "03b_module_item.png"), full_page=True)
        except Exception as e:
            print(f"  module-item err: {e}", flush=True)

        # Look for any button that might initiate the quiz
        print("\nHunting for launch buttons on current page...", flush=True)
        try:
            btns = await page.evaluate("""() => Array.from(document.querySelectorAll('button, a.btn, a.Button, a[role="button"], input[type="button"], input[type="submit"]')).map(b => ({
                tag: b.tagName,
                text: (b.innerText||b.value||'').slice(0,100),
                href: b.href || null,
                id: b.id || null,
                cls: (b.className||'').slice(0,100),
            }))""")
            (OUT / "buttons.json").write_text(json.dumps(btns, indent=2))
            interesting = [b for b in btns if any(k in (b['text'] or '').lower() for k in ['take','resume','start','retake','begin','launch'])]
            for b in interesting:
                print(f"  button: {b}", flush=True)
            if interesting:
                # Try clicking the first one
                label = interesting[0]['text']
                try:
                    await page.get_by_text(label, exact=False).first.click(timeout=5000)
                    await page.wait_for_timeout(12000)
                    print(f"  clicked '{label}' — new URL: {page.url}", flush=True)
                    (OUT / "04_after_click.html").write_text(await page.content())
                    await page.screenshot(path=str(OUT / "04_after_click.png"), full_page=True)
                    await dump_frame_tree(page, "04_after_click")
                    for f in page.frames:
                        if "quiz-lti" in (f.url or "") or "learnosity" in (f.url or ""):
                            await dump_learnosity_structure(f, "04_quiz_lti")
                except Exception as e:
                    print(f"  click err: {e}", flush=True)
        except Exception as e:
            print(f"  btn hunt err: {e}", flush=True)

        # Final frame dump across every frame, looking for learnosity inputs
        for f in page.frames:
            u = f.url or ""
            if "quiz-lti" in u or "learnosity" in u or "quiz-api" in u:
                print(f"  final-dump frame: {u[:120]}", flush=True)
                await dump_learnosity_structure(f, f"final_{hash(u)%10000}")

        await browser.close()
        print("Done.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
