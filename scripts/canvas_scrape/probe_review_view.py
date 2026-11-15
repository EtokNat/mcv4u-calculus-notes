"""Probe Canvas FC A for correct-answer source.

Two parallel strategies; both outputs saved for offline analysis:
  A) Canvas New Quizzes authoring API — /api/quiz/v1/courses/:cid/quizzes/:qid/items
     returns item-bank JSON with correct answers if account has teacher role.
  B) Submit the quiz with placeholder "1" in every blank, then scrape the
     post-submit review view — standard Learnosity SDK surfaces correct
     answers alongside student answers.

Target: FC A (assignment 14502) in course 616. Saves everything to ./review_probe/.
"""
import os, json, pathlib, asyncio, re
from playwright.async_api import async_playwright

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"
AID  = 14502   # Canvas assignment id for FC A Lessons 2.1 & 2.2
OUT  = pathlib.Path(os.environ.get("OUT_ROOT", "./review_probe")).resolve()
OUT.mkdir(parents=True, exist_ok=True)

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def save_state(page, tag):
    try:
        html = await page.content()
        (OUT / f"{tag}.html").write_text(html[:1500000])
    except Exception as e:
        (OUT / f"{tag}.html_err").write_text(str(e))
    (OUT / f"{tag}.url").write_text(page.url)
    try:
        await page.screenshot(path=str(OUT / f"{tag}.png"), full_page=True)
    except Exception:
        pass
    # Dump every frame's URL + a snippet of its text, since Learnosity lives in frames
    frames_info = []
    for f in page.frames:
        try:
            text = await f.evaluate("() => document.body ? document.body.innerText.slice(0, 2000) : ''")
        except Exception:
            text = ""
        frames_info.append({"name": f.name, "url": f.url, "text_snippet": text})
    (OUT / f"{tag}.frames.json").write_text(json.dumps(frames_info, indent=2))

async def try_teacher_api(page):
    """Strategy A: hit Canvas New Quizzes authoring API."""
    # First we need the actual quiz_id (not the assignment_id). Look it up via the
    # New Quizzes LTI launch or the course quizzes index.
    results = {}
    # Direct attempt with assignment id as quiz id — sometimes they match
    for guess_qid in [AID, "14502"]:
        for path in [
            f"/api/quiz/v1/courses/{CID}/quizzes/{guess_qid}/items",
            f"/api/quiz/v1/courses/{CID}/quizzes/{guess_qid}",
        ]:
            url = BASE + path
            try:
                r = await page.request.get(url)
                body = await r.text()
                results[f"GET {path}"] = {
                    "status": r.status,
                    "body": body[:5000],
                }
            except Exception as e:
                results[f"GET {path}"] = {"error": str(e)}

    # Alternative: try the /api/v1 Canvas quiz API (classic quizzes)
    for path in [
        f"/api/v1/courses/{CID}/assignments/{AID}",
        f"/api/v1/courses/{CID}/quizzes/{AID}",
        f"/api/v1/courses/{CID}/quizzes/{AID}/questions",
        f"/api/v1/courses/{CID}/assignments/{AID}/overrides",
    ]:
        url = BASE + path
        try:
            r = await page.request.get(url)
            body = await r.text()
            results[f"GET {path}"] = {
                "status": r.status,
                "body": body[:3000],
            }
        except Exception as e:
            results[f"GET {path}"] = {"error": str(e)}

    (OUT / "A_teacher_api.json").write_text(json.dumps(results, indent=2))
    print("  teacher API probes saved", flush=True)

async def discover_newquiz_id(page):
    """New Quizzes IDs are distinct from assignment IDs. Visit the assignment
    page as teacher — the embedded iframe URL contains the New Quiz id."""
    await page.goto(f"{BASE}/courses/{CID}/assignments/{AID}", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(8000)
    await save_state(page, "A_assignment_page")
    # Hunt in page HTML for quiz-lti URLs or new_quizzes/<id>
    html = await page.content()
    candidates = set(re.findall(r"new_quizzes?/(\d+)", html))
    candidates |= set(re.findall(r"quizzes/(\d+)/take", html))
    candidates |= set(re.findall(r"quiz[_-]?id['\"]?\s*[:=]\s*['\"]?(\d+)", html))
    # Also check iframe src attrs
    for f in page.frames:
        if 'quiz' in (f.url or '').lower():
            candidates |= set(re.findall(r'(\d{3,})', f.url))
    (OUT / "A_candidate_quiz_ids.txt").write_text("\n".join(sorted(candidates)))
    print(f"  candidate new-quiz ids: {sorted(candidates)[:10]}", flush=True)
    return sorted(candidates)

async def probe_review(page):
    """Strategy B: take quiz with placeholder answers, dump post-submit review view."""
    await page.goto(f"{BASE}/courses/{CID}/assignments/{AID}/launch",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(10000)
    await save_state(page, "B1_launch")

    # Click Begin
    try:
        await page.locator('[data-automation="sdk-start-resume-button"]').first.click(timeout=15000)
    except Exception:
        try:
            await page.get_by_role("button", name=re.compile("Begin|Resume|Start|Take", re.I)).first.click(timeout=8000)
        except Exception as e:
            print(f"  start-click err: {e}", flush=True)
    await page.wait_for_timeout(10000)
    await save_state(page, "B2_after_begin")

    try:
        await page.wait_for_selector('[data-automation="sdk-item-wrapper"]', timeout=30000)
    except Exception as e:
        print(f"  no items: {e}", flush=True)
        return

    # Dump questions
    questions = await page.evaluate("""() => {
        const wrappers = Array.from(document.querySelectorAll('[data-automation="sdk-item-wrapper"]'));
        return wrappers.map((w, i) => {
            const promptEl = w.querySelector('[data-automation="sdk-take-item-question"]');
            const inputs = Array.from(w.querySelectorAll('input[type="text"]'));
            return {
                idx: i,
                prompt: (promptEl?.innerText || w.innerText || '').slice(0, 3000),
                input_ids: inputs.map(el => el.id),
                wrapper_html: w.outerHTML.slice(0, 5000),
            };
        });
    }""")
    (OUT / "B3_questions.json").write_text(json.dumps(questions, indent=2))
    print(f"  saw {len(questions)} questions", flush=True)

    # Fill every text blank with "1" so submit is valid
    for q in questions:
        for input_id in q["input_ids"]:
            try:
                await page.locator(f"#{input_id}").fill("1", timeout=3000)
            except Exception:
                pass
    await save_state(page, "B4_before_submit")

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
        print(f"  submit err: {e}", flush=True)
    await page.wait_for_timeout(15000)
    await save_state(page, "B5_post_submit")

    # Try to navigate to the review view
    nav_tried = []
    for label in ["Review", "View Results", "See Results", "View My Results", "Review Results", "View Feedback"]:
        try:
            btn = page.get_by_role("button", name=re.compile(label, re.I))
            if await btn.count() > 0:
                await btn.first.click(timeout=5000)
                await page.wait_for_timeout(6000)
                nav_tried.append(f"button:{label}")
                break
        except Exception:
            continue
    for label in ["Review", "View Results", "See results", "Review your answers"]:
        try:
            link = page.get_by_role("link", name=re.compile(label, re.I))
            if await link.count() > 0:
                await link.first.click(timeout=5000)
                await page.wait_for_timeout(6000)
                nav_tried.append(f"link:{label}")
                break
        except Exception:
            continue
    (OUT / "B6_nav_tried.txt").write_text("\n".join(nav_tried))
    await save_state(page, "B7_review_view")

    # Brute-force selector dump on review view
    review = await page.evaluate("""() => {
        const data = {};
        const selectors = [
            '[data-automation="sdk-review-item-wrapper"]',
            '[data-automation="sdk-item-wrapper"]',
            '[data-automation*="review"]',
            '[data-automation*="correct"]',
            '[data-automation*="feedback"]',
            '[class*="review"]',
            '[class*="correct"]',
            '[class*="feedback"]',
            '[data-ref*="correct"]',
            '[data-ref*="answer"]',
            '.lrn_label_right',
            '.lrn_correct_response',
            '.lrn_response_correct',
            '.lrn_response_incorrect',
            '.lrn_answer_correct',
            '.lrn_answer_container',
            '.lrn-response-validate-wrapper',
        ];
        for (const sel of selectors) {
            const els = Array.from(document.querySelectorAll(sel));
            data[sel] = {
                count: els.length,
                samples: els.slice(0, 2).map(e => ({
                    outer: e.outerHTML.slice(0, 3000),
                    text: e.innerText?.slice(0, 1500),
                })),
            };
        }
        return data;
    }""")
    (OUT / "B8_review_selectors.json").write_text(json.dumps(review, indent=2))

    # Dive into every iframe that looks like Learnosity and dump inputs + their siblings
    for f in page.frames:
        tag = (f.name or f.url or 'anon').replace('/', '_').replace(':', '_')[:60]
        if not f.url:
            continue
        try:
            frame_data = await f.evaluate("""() => {
                const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
                return {
                    url: location.href,
                    input_count: inputs.length,
                    inputs: inputs.slice(0, 50).map(inp => ({
                        id: inp.id,
                        name: inp.name,
                        value: inp.value,
                        readonly: inp.readOnly,
                        classes: inp.className,
                        aria_label: inp.getAttribute('aria-label'),
                        parent_text: inp.parentElement?.innerText?.slice(0, 800),
                        parent_classes: inp.parentElement?.className,
                        next_text: inp.nextElementSibling?.innerText?.slice(0, 500),
                        next_classes: inp.nextElementSibling?.className,
                    })),
                    // Pull every textual mention of "correct" or "answer"
                    correct_text: (document.body?.innerText || '').match(/[^\\n]*(correct|answer)[^\\n]*/gi)?.slice(0, 30) || [],
                };
            }""")
            (OUT / f"B9_frame_{tag}.json").write_text(json.dumps(frame_data, indent=2))
        except Exception as e:
            (OUT / f"B9_frame_{tag}.err").write_text(str(e))

    # Save submission state via Canvas API
    try:
        r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/assignments/{AID}/submissions/self?include[]=submission_history")
        body = await r.json()
        (OUT / "B10_submission.json").write_text(json.dumps(body, indent=2, default=str))
    except Exception as e:
        (OUT / "B10_submission.err").write_text(str(e))

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 2400})
        page = await ctx.new_page()
        print("logging in...", flush=True)
        await login(page)
        print("Strategy A: teacher API probes...", flush=True)
        await try_teacher_api(page)
        candidates = await discover_newquiz_id(page)
        # Re-probe teacher API with candidate quiz ids
        extra = {}
        for qid in candidates[:8]:
            for path in [
                f"/api/quiz/v1/courses/{CID}/quizzes/{qid}/items",
                f"/api/quiz/v1/courses/{CID}/quizzes/{qid}",
            ]:
                url = BASE + path
                try:
                    r = await page.request.get(url)
                    body = await r.text()
                    extra[f"GET {path}"] = {"status": r.status, "body": body[:6000]}
                except Exception as e:
                    extra[f"GET {path}"] = {"error": str(e)}
        (OUT / "A2_teacher_api_candidates.json").write_text(json.dumps(extra, indent=2))

        print("Strategy B: submit + review view...", flush=True)
        await probe_review(page)

        await browser.close()
    print("DONE — outputs in", OUT, flush=True)

if __name__ == "__main__":
    asyncio.run(main())
