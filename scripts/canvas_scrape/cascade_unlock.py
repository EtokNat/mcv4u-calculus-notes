"""Cascade through every locked quiz_lti item in MCV4U, attempt to solve each,
log every (prompt, pattern, answers) to a per-unit markdown so the user gets a
teaching-ready question bank.

Per attempt:
  1. Launch assignment via /launch
  2. Click Begin/Resume
  3. Scrape 8 (or N) question prompts
  4. Solve each with solve_formative.solve_question
  5. Fill blanks + submit
  6. Poll for new score

If score >= min_score, mark done and move to next quiz_lti item.
If not, retry up to RETRY_PER_QUIZ times (each retry gets a fresh random draw).
If still failing, log the failure and continue to next item.
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
OUT  = pathlib.Path(os.environ.get("OUT_ROOT", "./cascade")).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RETRY_PER_QUIZ = int(os.environ.get("RETRY_PER_QUIZ", "5"))
BANK_DIR = OUT / "question_bank"
BANK_DIR.mkdir(parents=True, exist_ok=True)
SKIP_PATTERNS_IF_PRESENT = set((os.environ.get("SKIP_PATTERNS", "") or "").split(","))
STOP_AFTER = int(os.environ.get("STOP_AFTER", "0"))

STATE_FILE = OUT / "cascade_state.json"

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"quizzes": {}, "bank_hashes": []}

def save_state(st):
    STATE_FILE.write_text(json.dumps(st, indent=2, default=str))

def slug(s): return re.sub(r'[^A-Za-z0-9._-]+', '_', s)[:80]

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def fetch_quiz_lti_items(page):
    """All quiz_lti module items across every module, in (module_pos, item_pos) order."""
    r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/modules?per_page=50")
    modules = await r.json()
    rows = []
    for mi, m in enumerate(modules):
        mid = m["id"]
        r2 = await page.request.get(f"{BASE}/api/v1/courses/{CID}/modules/{mid}/items?per_page=100&include[]=content_details")
        items = await r2.json()
        for it in items:
            if not it.get("quiz_lti"):
                continue
            locked = (it.get("content_details") or {}).get("locked_for_user", True)
            cr = it.get("completion_requirement") or {}
            m_aid = re.search(r'/assignments/(\d+)', it.get("url",""))
            rows.append({
                "unit_pos": mi,
                "module_id": mid,
                "module_name": m["name"],
                "item_id": it["id"],
                "aid": int(m_aid.group(1)) if m_aid else None,
                "title": it["title"],
                "locked": locked,
                "completed": cr.get("completed"),
                "min_score": cr.get("min_score") or 60,
                "position": it.get("position") or 0,
            })
    rows.sort(key=lambda r: (r["unit_pos"], r["position"]))
    return rows, modules

async def submission_state(page, aid):
    r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/assignments/{aid}/submissions/self")
    try: return await r.json()
    except Exception: return {}

async def attempt_quiz(page, aid, mid, min_score, tag):
    """Single attempt; returns (score, questions_meta)."""
    await page.goto(f"{BASE}/courses/{CID}/assignments/{aid}/launch",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(5000)
    try:
        await page.locator('[data-automation="sdk-start-resume-button"]').first.click(timeout=15000)
    except Exception:
        try:
            await page.get_by_role("button", name=re.compile("Begin|Resume|Start|Take", re.I)).first.click(timeout=8000)
        except Exception as e:
            print(f"    [{tag}] start-click: {e}", flush=True)
    await page.wait_for_timeout(10000)
    try:
        await page.wait_for_selector('[data-automation="sdk-item-wrapper"]', timeout=30000)
    except Exception as e:
        print(f"    [{tag}] wait-items: {e}", flush=True)
        return None, []
    await page.wait_for_timeout(3000)

    questions = await page.evaluate("""() => {
        const wrappers = Array.from(document.querySelectorAll('[data-automation="sdk-item-wrapper"]'));
        return wrappers.map((w, i) => {
            const promptEl = w.querySelector('[data-automation="sdk-take-item-question"]');
            const inputs = Array.from(w.querySelectorAll('input[type="text"]'));
            return {
                idx: i,
                prompt: (promptEl?.innerText || w.innerText || '').slice(0, 3000),
                input_ids: inputs.map(el => el.id),
            };
        });
    }""")
    print(f"    [{tag}] {len(questions)} questions", flush=True)

    meta = []
    for q in questions:
        n = len(q["input_ids"])
        res = solve_question(q["prompt"], n)
        meta.append({
            "idx": q["idx"], "prompt": q["prompt"], "num_blanks": n,
            "pattern": res.get("pattern"), "ok": res.get("ok"),
            "answers": res.get("answers"), "reason": res.get("reason"),
        })
        if res.get("ok"):
            for input_id, ans in zip(q["input_ids"], res["answers"]):
                try:
                    await page.locator(f"#{input_id}").fill(str(ans), timeout=5000)
                except Exception as e:
                    print(f"      fill err {input_id}={ans}: {e}", flush=True)
        else:
            print(f"      Q{q['idx']+1} UNSOLVED pattern={res.get('pattern')} reason={res.get('reason')}", flush=True)

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
        print(f"    [{tag}] submit err: {e}", flush=True)
    await page.wait_for_timeout(8000)

    # Poll score
    best = None
    for _ in range(8):
        await page.wait_for_timeout(3000)
        s = await submission_state(page, aid)
        sc = s.get("score")
        if sc is not None:
            best = sc
            break
    return best, meta

def write_bank(unit_name: str, quiz_title: str, questions_meta: list, state_hashes: list):
    """Append each unique (prompt, answers) to the bank file for this unit."""
    unit_dir = BANK_DIR / slug(unit_name)
    unit_dir.mkdir(parents=True, exist_ok=True)
    f = unit_dir / f"{slug(quiz_title)}.md"
    existing = f.read_text() if f.exists() else f"# {quiz_title}\n\n**Unit:** {unit_name}\n\n"
    new_entries = []
    for q in questions_meta:
        if not q.get("ok"):
            continue
        h = str(hash(q["prompt"].strip()))
        if h in state_hashes:
            continue
        state_hashes.append(h)
        new_entries.append(q)
    if new_entries:
        with f.open("w") as out:
            out.write(existing)
            for q in new_entries:
                out.write(f"\n---\n\n## {q.get('pattern') or 'question'} ({q['num_blanks']} blanks)\n\n")
                out.write("**Prompt:**\n\n```\n" + q["prompt"].strip() + "\n```\n\n")
                out.write("**Answers:** " + ", ".join(f"`{a}`" for a in q["answers"]) + "\n")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 3200})
        page = await ctx.new_page()
        print("Login...", flush=True)
        await login(page)

        state = load_state()
        quizzes, _ = await fetch_quiz_lti_items(page)
        (OUT / "initial_quizzes.json").write_text(json.dumps(quizzes, indent=2, default=str))

        passed = 0
        attempted = 0
        skipped = 0
        for q in quizzes:
            qkey = str(q["item_id"])
            if q["completed"]:
                state["quizzes"][qkey] = {"status": "already_completed", "title": q["title"]}
                continue
            if q["locked"]:
                # need to re-check in case upstream unlocked this
                s = await submission_state(page, q["aid"])
                if s.get("workflow_state") in ("graded",) and (s.get("score") or 0) >= q["min_score"]:
                    state["quizzes"][qkey] = {"status": "already_passed", "score": s.get("score"), "title": q["title"]}
                    passed += 1
                    continue
            # Is it accessible?  Try launching it.
            print(f"\n→ {q['module_name']} · {q['title']} (aid={q['aid']}, min={q['min_score']})", flush=True)
            attempted += 1
            best_score = -1.0
            best_meta = []
            for retry in range(1, RETRY_PER_QUIZ + 1):
                try:
                    score, meta = await attempt_quiz(page, q["aid"], q["item_id"], q["min_score"], f"{q['item_id']}#r{retry}")
                except Exception as e:
                    print(f"    attempt exc: {e}", flush=True)
                    score, meta = None, []
                if meta: best_meta = meta
                if score is not None and score > best_score:
                    best_score = score
                print(f"    [r{retry}] score={score} best={best_score}", flush=True)
                if score is not None and score >= q["min_score"]:
                    passed += 1
                    break
            write_bank(q["module_name"], q["title"], best_meta, state["bank_hashes"])
            state["quizzes"][qkey] = {
                "title": q["title"], "best_score": best_score,
                "min_score": q["min_score"],
                "status": "passed" if best_score >= q["min_score"] else "failed",
            }
            save_state(state)
            if STOP_AFTER and attempted >= STOP_AFTER:
                print(f"\nSTOP_AFTER={STOP_AFTER} reached", flush=True)
                break

        # Final state
        final_quizzes, _ = await fetch_quiz_lti_items(page)
        (OUT / "final_quizzes.json").write_text(json.dumps(final_quizzes, indent=2, default=str))
        unlocked_count = sum(1 for q in final_quizzes if not q["locked"] or q["completed"])
        total = len(final_quizzes)
        print(f"\n=== DONE ===", flush=True)
        print(f"Attempted: {attempted}, passed: {passed}, skipped: {skipped}", flush=True)
        print(f"Final unlocked: {unlocked_count}/{total}", flush=True)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
