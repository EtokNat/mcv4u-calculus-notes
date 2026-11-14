"""Loop-attempt the Formative Check A submission using the SymPy solver.

Each attempt:
  1. Login + launch + start/resume quiz
  2. Scrape the 8 question prompts
  3. Solve each question with solve_formative.solve_question
  4. Log every (prompt, solved_answers) into attempts.json
  5. Fill the blanks and submit
  6. Read the new score

Loop until:
  - score >= 60, OR
  - MAX_ATTEMPTS reached
"""
import os, re, json, pathlib, asyncio, time, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from solve_formative import solve_question  # noqa: E402

from playwright.async_api import async_playwright

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"
AID  = int(os.environ.get("AID", "14503"))
MID  = int(os.environ.get("MID", "32373"))
OUT  = pathlib.Path(os.environ.get("OUT_ROOT", "./submit_fa")).resolve()
OUT.mkdir(parents=True, exist_ok=True)
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "8"))
PASS_SCORE = float(os.environ.get("PASS_SCORE", "60"))

ATTEMPT_LOG = OUT / "attempts.jsonl"
BANK_FILE   = OUT / "question_bank.jsonl"

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def submission_state(page):
    r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/assignments/{AID}/submissions/self")
    try:
        body = await r.json()
    except Exception:
        body = {"_raw": (await r.text())[:500]}
    return body

def log_bank(prompt: str, pattern: str, answers: list):
    """Append each unique question (hashed) to the question bank jsonl."""
    key = str(hash(prompt.strip()))
    rec = {"hash": key, "pattern": pattern, "prompt": prompt, "answers": answers}
    with BANK_FILE.open("a") as f:
        f.write(json.dumps(rec) + "\n")

def already_seen_hashes():
    seen = set()
    if BANK_FILE.exists():
        for line in BANK_FILE.read_text().splitlines():
            try: seen.add(json.loads(line)["hash"])
            except Exception: pass
    return seen

async def do_attempt(ctx, attempt_idx: int):
    page = await ctx.new_page()
    try:
        await login(page)
        before = await submission_state(page)
        print(f"  [a{attempt_idx}] before: score={before.get('score')} ws={before.get('workflow_state')}", flush=True)

        await page.goto(f"{BASE}/courses/{CID}/assignments/{AID}/launch",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # Click start/resume
        try:
            await page.locator('[data-automation="sdk-start-resume-button"]').first.click(timeout=15000)
        except Exception:
            try:
                await page.get_by_role("button", name=re.compile("Begin|Resume|Start|Take", re.I)).first.click(timeout=8000)
            except Exception as e:
                print(f"    start-click failed: {e}", flush=True)
        await page.wait_for_timeout(10000)

        try:
            await page.wait_for_selector('[data-automation="sdk-item-wrapper"]', timeout=30000)
        except Exception as e:
            print(f"    wait-items failed: {e}", flush=True)
            await page.screenshot(path=str(OUT / f"a{attempt_idx}_no_items.png"), full_page=True)
            return None

        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(OUT / f"a{attempt_idx}_01_loaded.png"), full_page=True)

        questions = await page.evaluate("""() => {
            const wrappers = Array.from(document.querySelectorAll('[data-automation="sdk-item-wrapper"]'));
            return wrappers.map((w, i) => {
                const promptEl = w.querySelector('[data-automation="sdk-take-item-question"]');
                const inputs = Array.from(w.querySelectorAll('input[type="text"]'));
                return {
                    idx: i,
                    prompt: (promptEl?.innerText || w.innerText || '').slice(0, 2000),
                    input_ids: inputs.map(el => el.id),
                };
            });
        }""")
        print(f"    found {len(questions)} questions", flush=True)

        attempt_rec = {"attempt": attempt_idx, "questions": [], "ts": int(time.time())}
        seen = already_seen_hashes()

        for q in questions:
            n = len(q["input_ids"])
            res = solve_question(q["prompt"], n)
            # If solver OK, fill inputs; otherwise skip (partial credit from other questions)
            entry = {
                "idx": q["idx"], "prompt": q["prompt"], "num_blanks": n,
                "pattern": res.get("pattern"), "ok": res.get("ok"),
                "answers": res.get("answers"), "reason": res.get("reason"),
            }
            attempt_rec["questions"].append(entry)
            if res.get("ok"):
                # Log to bank (dedupe by prompt hash)
                h = str(hash(q["prompt"].strip()))
                if h not in seen:
                    log_bank(q["prompt"], res["pattern"], res["answers"])
                    seen.add(h)
                # Fill
                for input_id, ans in zip(q["input_ids"], res["answers"]):
                    try:
                        await page.locator(f"#{input_id}").fill(str(ans), timeout=5000)
                    except Exception as e:
                        print(f"    fill err {input_id}={ans}: {e}", flush=True)
            else:
                print(f"    Q{q['idx']+1} UNSOLVED: pattern={res.get('pattern')} reason={res.get('reason')}", flush=True)

        with ATTEMPT_LOG.open("a") as f:
            f.write(json.dumps(attempt_rec) + "\n")

        await page.screenshot(path=str(OUT / f"a{attempt_idx}_02_filled.png"), full_page=True)

        # Submit
        try:
            await page.locator('[data-automation="sdk-submit-button"]').first.click(timeout=10000)
            await page.wait_for_timeout(3000)
            for label in ["Submit", "Yes", "Confirm", "OK"]:
                try:
                    btn = page.get_by_role("button", name=label, exact=False)
                    if await btn.count() > 0:
                        await btn.first.click(timeout=3000)
                        await page.wait_for_timeout(2000)
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"    submit err: {e}", flush=True)

        await page.wait_for_timeout(8000)
        await page.screenshot(path=str(OUT / f"a{attempt_idx}_03_submitted.png"), full_page=True)

        # Poll for score
        after = None
        for i in range(8):
            await page.wait_for_timeout(3000)
            after = await submission_state(page)
            if after.get("score") is not None and after.get("score") != before.get("score"):
                break
        new_score = after.get("score") if after else None
        print(f"  [a{attempt_idx}] after: score={new_score}", flush=True)
        return new_score
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 3200})
        best = -1.0
        for i in range(1, MAX_ATTEMPTS + 1):
            print(f"\n=== Attempt {i}/{MAX_ATTEMPTS} ===", flush=True)
            try:
                score = await do_attempt(ctx, i)
            except Exception as e:
                print(f"  attempt {i} exc: {e}", flush=True)
                score = None
            if score is not None and score > best:
                best = score
            if score is not None and score >= PASS_SCORE:
                print(f"\nPASS: score={score} >= {PASS_SCORE}", flush=True)
                break
        else:
            print(f"\nStopped after {MAX_ATTEMPTS} attempts; best={best}", flush=True)
        await browser.close()

        # Final module-item check
        # (Need a fresh page for auth; create one)
        # Skipped: our workflow runs submissions/self polling already.

        # Summary
        bank_lines = BANK_FILE.read_text().splitlines() if BANK_FILE.exists() else []
        print(f"\nQuestion bank: {len(bank_lines)} unique prompts collected.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
