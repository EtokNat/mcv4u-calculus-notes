"""Submit Formative Check A (assignment 14503) with computed answers.

Flow:
  1. Login, go to /launch, click Begin.
  2. Wait for 8 sdk-item-wrapper containers to render.
  3. For each question (in DOM order), extract prompt text + list all inputs inside the wrapper.
     Use prompt text to look up the answer list in ANSWERS. Fill inputs positionally.
  4. Click sdk-submit-button, confirm any modal, read the result page.
  5. Poll submissions/self for the new score.

Unlimited attempts, so a wrong-format submission is recoverable. We dump the full input→answer
plan to disk BEFORE typing so you can audit.
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
DRY  = os.environ.get("DRY_RUN", "").lower() in ("1","true","yes")

# Answers for each question — matched by substring in question prompt.
# Each entry: (match_substring, [ordered blank answers])
# Order within the list matches the ORDER THE INPUTS APPEAR inside that question's wrapper.
ANSWERS = [
    ("product of each radical expression",       ["3", "37", "61", "5"]),
    ("slope of the line through each pair",      ["3", "-5/3", "-1/3"]),
    ("slope of a line perpendicular",            ["-1/3", "-7/13"]),
    ("slope of the demand curve",                ["-5/4"]),
    ("slope of the tangent to each curve at the given point",
                                                 ["1", "-1", "9", "1/6", "-3/4", "-1/6"]),
    ("slope of the tangent at x = 4",            ["-31"]),
    ("circulation of a local newspaper",         ["500"]),
    ("slope of the tangent to each curve at the given value of x",
                                                 ["-2", "-1/2", "-1/25"]),
]

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def submission_state(page, tag):
    r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/assignments/{AID}/submissions/self")
    try:
        body = await r.json()
    except Exception:
        body = {"_raw": (await r.text())[:500]}
    (OUT / f"submission_{tag}.json").write_text(json.dumps({"status": r.status, "body": body}, indent=2, default=str))
    ws = body.get("workflow_state") if isinstance(body, dict) else "?"
    score = body.get("score") if isinstance(body, dict) else "?"
    print(f"  submission[{tag}]: HTTP {r.status} workflow_state={ws} score={score}", flush=True)
    return body

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 3200})
        page = await ctx.new_page()
        print("Logging in...", flush=True)
        await login(page)
        await submission_state(page, "before")

        print("Launching quiz LTI...", flush=True)
        await page.goto(f"{BASE}/courses/{CID}/assignments/{AID}/launch",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # Click Begin / Resume / Start (whichever button is present)
        try:
            await page.locator('[data-automation="sdk-start-resume-button"]').first.click(timeout=15000)
            print("  clicked start-resume-button", flush=True)
        except Exception as e:
            print(f"  start-resume err: {e}", flush=True)
            try:
                await page.get_by_role("button", name=re.compile("Begin|Resume|Start|Take", re.I)).first.click(timeout=8000)
                print("  clicked by role regex", flush=True)
            except Exception as e2:
                print(f"  role click err: {e2}", flush=True)
        await page.wait_for_timeout(10000)

        # Wait for the 8 question wrappers
        try:
            await page.wait_for_selector('[data-automation="sdk-item-wrapper"]', timeout=30000)
        except Exception as e:
            (OUT / "wait_err.txt").write_text(str(e))
        await page.wait_for_timeout(3000)

        await page.screenshot(path=str(OUT / "10_before_fill.png"), full_page=True)
        (OUT / "10_before_fill.html").write_text(await page.content())

        # Extract each question block: prompt text + input element handles
        questions = await page.evaluate("""() => {
            const wrappers = Array.from(document.querySelectorAll('[data-automation="sdk-item-wrapper"]'));
            return wrappers.map((w, i) => {
                const promptEl = w.querySelector('[data-automation="sdk-take-item-question"]');
                const inputs = Array.from(w.querySelectorAll('input[type="text"]'));
                return {
                    idx: i,
                    prompt: (promptEl?.innerText || w.innerText || '').slice(0, 1000),
                    input_ids: inputs.map(el => el.id),
                    input_types: inputs.map(el => el.getAttribute('role') || el.getAttribute('data-automation') || el.type),
                };
            });
        }""")
        (OUT / "20_question_layout.json").write_text(json.dumps(questions, indent=2))
        print(f"  found {len(questions)} questions", flush=True)

        # Build fill plan
        plan = []
        for q in questions:
            prompt = q["prompt"].lower()
            match = None
            for sub, ans_list in ANSWERS:
                if sub.lower() in prompt:
                    match = (sub, ans_list)
                    break
            if match is None:
                plan.append({"idx": q["idx"], "status": "NO_MATCH", "prompt_head": q["prompt"][:200]})
                continue
            sub, ans_list = match
            if len(ans_list) != len(q["input_ids"]):
                plan.append({
                    "idx": q["idx"], "status": "COUNT_MISMATCH",
                    "match": sub, "expected": len(ans_list), "got": len(q["input_ids"]),
                    "input_ids": q["input_ids"],
                    "prompt_head": q["prompt"][:300],
                })
            else:
                plan.append({
                    "idx": q["idx"], "status": "OK", "match": sub,
                    "fill": list(zip(q["input_ids"], ans_list)),
                })
        (OUT / "21_fill_plan.json").write_text(json.dumps(plan, indent=2))
        bad = [p for p in plan if p["status"] != "OK"]
        print(f"  plan: {len(plan)-len(bad)} OK, {len(bad)} issues", flush=True)
        for b in bad:
            print(f"    issue: {b}", flush=True)

        if DRY:
            print("DRY_RUN — not filling or submitting.", flush=True)
            await browser.close()
            return

        # Fill
        for p_entry in plan:
            if p_entry["status"] != "OK":
                continue
            for input_id, ans in p_entry["fill"]:
                try:
                    await page.locator(f"#{input_id}").fill(str(ans), timeout=5000)
                except Exception as e:
                    print(f"    fill err {input_id}={ans}: {e}", flush=True)

        await page.screenshot(path=str(OUT / "30_filled.png"), full_page=True)
        (OUT / "30_filled.html").write_text(await page.content())

        # Submit
        print("Submitting...", flush=True)
        try:
            await page.locator('[data-automation="sdk-submit-button"]').first.click(timeout=10000)
            await page.wait_for_timeout(3000)
            # Confirmation modal — click Submit again if present
            for label in ["Submit", "Yes", "Confirm", "OK"]:
                try:
                    btn = page.get_by_role("button", name=label, exact=False)
                    if await btn.count() > 0:
                        await btn.first.click(timeout=3000)
                        print(f"  clicked modal '{label}'", flush=True)
                        await page.wait_for_timeout(2000)
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"  submit err: {e}", flush=True)

        await page.wait_for_timeout(8000)
        await page.screenshot(path=str(OUT / "40_after_submit.png"), full_page=True)
        (OUT / "40_after_submit.html").write_text(await page.content())

        # Poll for score
        for i in range(6):
            await page.wait_for_timeout(5000)
            await submission_state(page, f"after_{i}")

        # Check module item completion
        try:
            r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/modules/3177/items?include[]=content_details")
            items = await r.json()
            (OUT / "module_items_after.json").write_text(json.dumps(items, indent=2, default=str))
            for it in items:
                if it.get("id") == MID:
                    cr = it.get("completion_requirement") or {}
                    print(f"  module_item {MID}: completed={cr.get('completed')} type={cr.get('type')} min={cr.get('min_score')}", flush=True)
        except Exception as e:
            (OUT / "module_items_err.txt").write_text(str(e))

        await browser.close()
        print("Done.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
