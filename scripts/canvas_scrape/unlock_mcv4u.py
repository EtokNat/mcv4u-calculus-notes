"""MCV4U Canvas unlocker — walks every module, saves content, submits quizzes to unlock the next item.

Resumable: state file at ./mcv4u_scrape/unlock_state.json. Rerunning skips items already marked done.

Env vars required:
    BRONSTON_USER = giscounsellor02@gmail.com
    BRONSTON_PASS = (password)

Optional env vars:
    ONLY_MODULE   = canvas module id (int) to restrict to a single module
    STOP_AT       = stop after N items in this run
    OUT_ROOT      = override output root (default: ./mcv4u_scrape)
    CID           = Canvas course id (default: 616)
    HEADLESS      = "0" to run with a display (needs xvfb), default "1"
"""
import os, re, sys, json, time, asyncio, pathlib, traceback
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from solve_formative import solve_question  # noqa: E402

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = os.environ.get("CID", "616")
ROOT = pathlib.Path(os.environ.get("OUT_ROOT", "./mcv4u_scrape")).resolve()
UNLOCKED = ROOT / f"course_{CID}" / "unlocked_items"
UNLOCKED.mkdir(parents=True, exist_ok=True)
BANK = ROOT / "question_bank"
BANK.mkdir(parents=True, exist_ok=True)
STATE_FILE = ROOT / "unlock_state.json"
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
RETRY_PER_QUIZ = int(os.environ.get("RETRY_PER_QUIZ", "5"))
MAX_PASSES = int(os.environ.get("MAX_PASSES", "6"))

def slug(s):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', str(s))[:100]

def load_state():
    if STATE_FILE.exists():
        s = json.loads(STATE_FILE.read_text())
        s.setdefault("bank_hashes", [])
        s.setdefault("quiz_scores", {})
        return s
    return {"done": {}, "errors": {}, "bank_hashes": [], "quiz_scores": {}}

def save_state(st):
    STATE_FILE.write_text(json.dumps(st, indent=2))

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def get_modules(page):
    url = f"{BASE}/api/v1/courses/{CID}/modules?include[]=items&include[]=content_details&per_page=100"
    r = await page.request.get(url)
    data = await r.json()
    out = list(data) if isinstance(data, list) else [data]
    while True:
        link = r.headers.get("link", "")
        nxt = None
        for part in link.split(","):
            if 'rel="next"' in part:
                nxt = part.split(";")[0].strip().strip("<>")
                break
        if not nxt:
            break
        r = await page.request.get(nxt)
        out.extend(await r.json())
    return out

async def safe_content(page, out_dir, name):
    """Save HTML + text + a screenshot, swallowing any errors."""
    try:
        (out_dir / f"{name}.html").write_text(await page.content())
    except Exception as e:
        (out_dir / f"{name}.html.error").write_text(str(e))
    try:
        (out_dir / f"{name}.txt").write_text(await page.inner_text("body", timeout=8000))
    except Exception as e:
        (out_dir / f"{name}.txt.error").write_text(str(e))
    try:
        await page.screenshot(path=str(out_dir / f"{name}.png"), full_page=True, timeout=10000)
    except Exception as e:
        (out_dir / f"{name}.png.error").write_text(str(e))

async def process_page_item(page, out_dir):
    await safe_content(page, out_dir, "content")
    try:
        main_html = await page.locator(".user_content, #wiki_page_show").first.inner_html(timeout=4000)
        (out_dir / "main.html").write_text(main_html)
    except Exception:
        pass
    return "page_viewed"

async def submission_state(page, aid):
    try:
        r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/assignments/{aid}/submissions/self")
        return await r.json()
    except Exception:
        return {}

def write_bank(module_name, quiz_title, questions_meta, state):
    unit_dir = BANK / slug(module_name)
    unit_dir.mkdir(parents=True, exist_ok=True)
    f = unit_dir / f"{slug(quiz_title)}.md"
    existing = f.read_text() if f.exists() else f"# {quiz_title}\n\n**Unit:** {module_name}\n\n"
    new_entries = []
    for q in questions_meta:
        if not q.get("ok"):
            continue
        h = str(hash(q["prompt"].strip()))
        if h in state["bank_hashes"]:
            continue
        state["bank_hashes"].append(h)
        new_entries.append(q)
    if new_entries:
        with f.open("w") as out:
            out.write(existing)
            for q in new_entries:
                out.write(f"\n---\n\n## {q.get('pattern') or 'question'} ({q['num_blanks']} blanks)\n\n")
                out.write("**Prompt:**\n\n```\n" + q["prompt"].strip() + "\n```\n\n")
                out.write("**Answers:** " + ", ".join(f"`{a}`" for a in q["answers"]) + "\n")

async def _attempt_learnosity(page, aid, out_dir, tag):
    """Single attempt at a Learnosity-rendered quiz. Returns (score, meta)."""
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
    best = None
    for _ in range(8):
        await page.wait_for_timeout(3000)
        s = await submission_state(page, aid)
        sc = s.get("score")
        if sc is not None:
            best = sc
            break
    return best, meta

async def process_quiz_lti(page, item, out_dir, state, module_name):
    """New-Quiz (Learnosity) item: retry until passing min_score."""
    aid_m = re.search(r'/assignments/(\d+)', item.get("url", "") or "")
    if not aid_m:
        return "quiz_lti_no_aid"
    aid = int(aid_m.group(1))
    cr = item.get("completion_requirement") or {}
    min_score = cr.get("min_score") or 60
    title = item.get("title", f"quiz_{aid}")
    (out_dir / "quiz_lti.json").write_text(json.dumps({"aid": aid, "min_score": min_score}, indent=2))
    # Already passed?
    s = await submission_state(page, aid)
    if (s.get("score") or -1) >= min_score:
        state["quiz_scores"][str(item["id"])] = s.get("score")
        return f"quiz_lti_already_passed:{s.get('score')}"
    best_score = -1.0
    best_meta = []
    for retry in range(1, RETRY_PER_QUIZ + 1):
        try:
            score, meta = await _attempt_learnosity(page, aid, out_dir, f"{item['id']}#r{retry}")
        except Exception as e:
            print(f"    attempt exc: {e}", flush=True)
            score, meta = None, []
        if meta:
            best_meta = meta
        if score is not None and score > best_score:
            best_score = score
        print(f"    [r{retry}] score={score} best={best_score}", flush=True)
        if score is not None and score >= min_score:
            break
    write_bank(module_name, title, best_meta, state)
    state["quiz_scores"][str(item["id"])] = best_score
    (out_dir / "attempts_meta.json").write_text(json.dumps(best_meta, indent=2, default=str))
    return f"quiz_lti_passed:{best_score}" if best_score >= min_score else f"quiz_lti_failed:{best_score}"

async def process_quiz_item(page, out_dir):
    """New Quizzes (Learnosity): click Begin, dump all questions on one page, submit."""
    try:
        begin = page.locator('button:has-text("Begin")')
        if await begin.count() > 0:
            await begin.first.click(timeout=10000)
            await page.wait_for_timeout(6000)  # Learnosity boot
            await safe_content(page, out_dir, "questions")
        else:
            # Already in progress or results view
            await safe_content(page, out_dir, "questions_no_begin")
    except Exception as e:
        (out_dir / "begin.error").write_text(traceback.format_exc())
        return f"begin_err:{e}"
    # Submit
    try:
        submit_btn = page.locator('button:has-text("Submit")')
        if await submit_btn.count() == 0:
            return "no_submit_button"
        await submit_btn.last.click(timeout=10000)
        await page.wait_for_timeout(2500)
        # Confirmation modal: button in a dialog
        for sel in ['[role="dialog"] button:has-text("Submit")',
                    '[role="alertdialog"] button:has-text("Submit")',
                    'button:has-text("Yes"):visible',
                    'button:has-text("Submit"):visible']:
            try:
                b = page.locator(sel).first
                if await b.count() > 0:
                    await b.click(timeout=4000)
                    break
            except Exception:
                continue
        await page.wait_for_timeout(4000)
        await safe_content(page, out_dir, "post_submit")
        return "quiz_submitted"
    except Exception as e:
        (out_dir / "submit.error").write_text(traceback.format_exc())
        return f"submit_err:{e}"

async def process_h5p_assignment(page, out_dir):
    """H5P LTI external_tool assignment: dump H5PIntegration + call player's
    triggerXAPIScored to fire a completion through H5P's own channel."""
    await safe_content(page, out_dir, "content")
    # Wait for H5P iframe to boot
    await page.wait_for_timeout(10000)
    # Find the launch frame (bronston.h5p.com)
    launch_frame = None
    for f in page.frames:
        if "h5p.com" in (f.url or "") and "lti" in (f.url or ""):
            launch_frame = f
            break
    if not launch_frame:
        return "no_h5p_launch_frame"
    # Dump H5PIntegration for content/questions/correct answers
    try:
        h5p_int = await launch_frame.evaluate(
            "() => (typeof H5PIntegration !== 'undefined') ? JSON.parse(JSON.stringify(H5PIntegration)) : null"
        )
        if h5p_int:
            (out_dir / "h5p_integration.json").write_text(json.dumps(h5p_int, indent=2, default=str))
    except Exception as e:
        (out_dir / "h5p_integration.error").write_text(str(e))
    # Find the inner content frame (h5p-iframe-<cid>)
    content_frame = None
    for f in page.frames:
        if f.name and f.name.startswith("h5p-iframe-"):
            content_frame = f
            break
    if not content_frame:
        return "no_h5p_content_frame"
    # Wait a bit longer for H5P instance to initialize
    for _ in range(6):
        ready = await content_frame.evaluate(
            "() => (typeof H5P !== 'undefined' && Array.isArray(H5P.instances) && H5P.instances.length > 0)"
        )
        if ready:
            break
        await page.wait_for_timeout(2000)
    # Trigger scored completion
    trig = await content_frame.evaluate(
        """() => {
            try {
                if (typeof H5P === 'undefined' || !H5P.instances || !H5P.instances.length) return {err: 'no_instance'};
                const inst = H5P.instances[0];
                const info = {lib: inst.libraryInfo && inst.libraryInfo.versionedNameNoSpaces};
                if (typeof inst.triggerXAPIScored === 'function') {
                    inst.triggerXAPIScored(1, 1, 'completed', true, true);
                    info.triggered = 'scored';
                } else if (typeof inst.triggerXAPICompleted === 'function') {
                    inst.triggerXAPICompleted();
                    info.triggered = 'completed';
                } else if (typeof inst.triggerXAPI === 'function') {
                    inst.triggerXAPI('completed');
                    info.triggered = 'xapi';
                } else {
                    info.err = 'no_trigger_method';
                }
                return info;
            } catch(e) { return {err: String(e)}; }
        }"""
    )
    (out_dir / "h5p_trigger.json").write_text(json.dumps(trig, indent=2))
    # Give H5P → Canvas AGS a moment to propagate
    await page.wait_for_timeout(5000)
    if trig.get("err"):
        return f"h5p_err:{trig.get('err')}"
    return f"h5p_triggered:{trig.get('lib')}"

async def _canvas_api_fetch(page, endpoint, method="POST", body=None, content_type="application/json", extra_headers=None):
    """Run an authenticated fetch inside the page so session cookies + CSRF are attached.

    Returns {status, csrf_used, body}. body may be dict (for JSON) or string.
    """
    return await page.evaluate(
        """async ({endpoint, method, body, content_type, extra}) => {
            let csrf = null;
            const meta = document.querySelector('meta[name="csrf-token"]');
            if (meta) csrf = meta.content;
            if (!csrf) {
                const m = document.cookie.match(/_csrf_token=([^;]+)/);
                if (m) csrf = decodeURIComponent(m[1]);
            }
            const headers = {'Accept':'application/json+canvas-string-ids, application/json','X-Requested-With':'XMLHttpRequest'};
            if (content_type) headers['Content-Type'] = content_type;
            if (csrf) headers['X-CSRF-Token'] = csrf;
            if (extra) for (const k in extra) headers[k] = extra[k];
            const init = {method, credentials:'include', headers};
            if (body !== null && body !== undefined) {
                init.body = (typeof body === 'string') ? body : JSON.stringify(body);
            }
            const r = await fetch(endpoint, init);
            const text = await r.text();
            return {status: r.status, csrf_used: !!csrf, body: text.slice(0, 4000)};
        }""",
        {"endpoint": endpoint, "method": method, "body": body, "content_type": content_type, "extra": extra_headers},
    )


async def submit_assignment_online_upload(page, assignment_id, out_dir, filename="submission.txt", content="Submitted for completion."):
    """Three-step Canvas upload: reserve slot → PUT file bytes → confirm + submit."""
    step1 = await _canvas_api_fetch(
        page,
        f"{BASE}/api/v1/courses/{CID}/assignments/{assignment_id}/submissions/self/files",
        method="POST",
        body={"name": filename, "size": len(content.encode()), "content_type": "text/plain"},
    )
    (out_dir / "upload_step1.json").write_text(json.dumps(step1, indent=2))
    if not (200 <= (step1.get("status") or 0) < 300):
        return f"upload_reserve_failed:{step1.get('status')}"
    try:
        reserve = json.loads(step1["body"])
    except Exception:
        return "upload_reserve_badjson"
    upload_url = reserve.get("upload_url")
    upload_params = reserve.get("upload_params") or {}
    if not upload_url:
        return "upload_no_url"
    step2 = await page.evaluate(
        """async ({upload_url, params, filename, content}) => {
            const fd = new FormData();
            for (const k in params) fd.append(k, params[k]);
            fd.append('file', new Blob([content], {type:'text/plain'}), filename);
            const r = await fetch(upload_url, {method:'POST', credentials:'include', body: fd});
            const text = await r.text();
            let json = null; try { json = JSON.parse(text); } catch(_) {}
            return {status: r.status, body: text.slice(0, 2000), json};
        }""",
        {"upload_url": upload_url, "params": upload_params, "filename": filename, "content": content},
    )
    (out_dir / "upload_step2.json").write_text(json.dumps(step2, indent=2))
    if not (200 <= (step2.get("status") or 0) < 400):
        return f"upload_put_failed:{step2.get('status')}"
    file_id = None
    if step2.get("json"):
        file_id = step2["json"].get("id")
    if not file_id:
        try:
            file_id = json.loads(step2["body"]).get("id")
        except Exception:
            pass
    if not file_id:
        return "upload_no_file_id"
    step3 = await _canvas_api_fetch(
        page,
        f"{BASE}/api/v1/courses/{CID}/assignments/{assignment_id}/submissions",
        method="POST",
        body={"submission": {"submission_type": "online_upload", "file_ids": [file_id]}},
    )
    (out_dir / "upload_step3.json").write_text(json.dumps(step3, indent=2))
    if 200 <= (step3.get("status") or 0) < 300:
        return f"assignment_api_submitted:file_id={file_id}"
    return f"upload_submit_failed:{step3.get('status')}"


async def process_assignment_text(page, item, out_dir):
    """Non-quiz assignment: prefer Canvas submission API (text entry → file upload fallback), then UI."""
    await safe_content(page, out_dir, "content")
    aid = item.get("content_id")
    if aid:
        # 1. Try online_text_entry via API — simplest, works if assignment accepts it.
        txt = await _canvas_api_fetch(
            page,
            f"{BASE}/api/v1/courses/{CID}/assignments/{aid}/submissions",
            method="POST",
            body={"submission": {"submission_type": "online_text_entry", "body": "Submitted for completion."}},
        )
        (out_dir / "text_submit_api.json").write_text(json.dumps(txt, indent=2))
        if 200 <= (txt.get("status") or 0) < 300:
            return f"text_submit_api:{txt.get('status')}"
        # 2. Fall back to file upload (3-step) — needed when assignment requires online_upload/media_recording.
        upload_result = await submit_assignment_online_upload(page, aid, out_dir)
        if upload_result.startswith("assignment_api_submitted"):
            return upload_result
        (out_dir / "assignment_api.summary").write_text(f"text_entry: {txt.get('status')}\nupload: {upload_result}\n")
    # Start Assignment button, if present
    for sel in ['a:has-text("Start Assignment")',
                'button:has-text("Start Assignment")',
                'a:has-text("Submit Assignment")',
                'button:has-text("Submit Assignment")',
                'a.btn-primary:has-text("Submit")']:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click(timeout=6000)
                await page.wait_for_timeout(2000)
                break
        except Exception:
            continue
    # Click Text Entry tab if a tab UI is shown
    try:
        tab = page.locator('a:has-text("Text Entry"), button:has-text("Text")').first
        if await tab.count() > 0:
            await tab.click(timeout=3000)
            await page.wait_for_timeout(1500)
    except Exception:
        pass
    filled = False
    for sel in ['.tox-edit-area iframe',
                'textarea[name="submission[body]"]',
                'textarea:visible']:
        try:
            if sel.endswith("iframe"):
                frame = page.frame_locator(sel).first
                body = frame.locator('body#tinymce, body').first
                await body.click(timeout=3000)
                await page.keyboard.type("Submitted.")
                filled = True
                break
            else:
                t = page.locator(sel).first
                if await t.count() > 0:
                    await t.fill("Submitted.", timeout=3000)
                    filled = True
                    break
        except Exception:
            continue
    # Submit
    try:
        sub = page.locator('button:has-text("Submit Assignment"), input[value="Submit Assignment"]').first
        if await sub.count() > 0:
            await sub.click(timeout=6000)
            await page.wait_for_timeout(3000)
            return f"text_submitted(filled={filled})"
    except Exception as e:
        (out_dir / "text_submit.error").write_text(traceback.format_exc())
        return f"text_submit_err:{e}"
    return f"no_text_submit_button(filled={filled})"

async def process_discussion_item(page, item, out_dir):
    await safe_content(page, out_dir, "content")
    topic_id = item.get("content_id")
    if not topic_id:
        for src in (item.get("url", ""), item.get("html_url", ""), page.url):
            m = re.search(r"/discussion_topics/(\d+)", src or "")
            if m:
                topic_id = m.group(1)
                break
    if topic_id:
        try:
            result = await page.evaluate(
                """async ({endpoint, message}) => {
                    let csrf = null;
                    const meta = document.querySelector('meta[name="csrf-token"]');
                    if (meta) csrf = meta.content;
                    if (!csrf) {
                        const match = document.cookie.match(/_csrf_token=([^;]+)/);
                        if (match) csrf = decodeURIComponent(match[1]);
                    }
                    const headers = {'Content-Type':'application/json','Accept':'application/json+canvas-string-ids, application/json','X-Requested-With':'XMLHttpRequest'};
                    if (csrf) headers['X-CSRF-Token'] = csrf;
                    const r = await fetch(endpoint, {method:'POST', credentials:'include', headers, body: JSON.stringify({message})});
                    const text = await r.text();
                    return {status: r.status, csrf_used: !!csrf, body: text.slice(0, 2000)};
                }""",
                {
                    "endpoint": f"{BASE}/api/v1/courses/{CID}/discussion_topics/{topic_id}/entries",
                    "message": "Engaging with this unit — looking forward to the lessons.",
                },
            )
            (out_dir / "discussion_api.json").write_text(json.dumps(result, indent=2))
            if isinstance(result, dict) and 200 <= (result.get("status") or 0) < 300:
                return f"discussion_api_posted:{topic_id}"
        except Exception as e:
            (out_dir / "discussion_api.error").write_text(traceback.format_exc())
    try:
        reply = page.locator('button:has-text("Reply"), a:has-text("Reply")').first
        if await reply.count() == 0:
            return "no_reply_button"
        await reply.click(timeout=5000)
        await page.wait_for_timeout(2000)
        for sel in ['.tox-edit-area iframe', 'textarea:visible']:
            try:
                if sel.endswith("iframe"):
                    frame = page.frame_locator(sel).first
                    body = frame.locator('body').first
                    await body.click(timeout=3000)
                    await page.keyboard.type("Noted. Looking forward to engaging with this unit.")
                    break
                else:
                    t = page.locator(sel).first
                    if await t.count() > 0:
                        await t.fill("Noted.", timeout=3000)
                        break
            except Exception:
                continue
        post = page.locator('button:has-text("Post Reply"), button:has-text("Reply"), input[value*="Reply"]').last
        if await post.count() > 0:
            await post.click(timeout=5000)
            await page.wait_for_timeout(3000)
            return "discussion_posted_ui"
        return "no_post_button"
    except Exception as e:
        (out_dir / "discussion.error").write_text(traceback.format_exc())
        return f"discussion_err:{e}"

async def process_item(page, item, state, module_name=""):
    """Hardened: any failure sets a state entry and never silently drops the loop."""
    key = str(item["id"])
    prev = state["done"].get(key, "")
    # Retry LOCKED, failed quizzes, and transient errors on subsequent passes.
    retriable = (
        prev.startswith("LOCKED")
        or prev.startswith("quiz_lti_failed")
        or prev.startswith("FATAL")
        or prev.startswith("begin_err")
        or prev.startswith("submit_err")
        or prev in ("discussion_posted", "no_reply_button", "no_post_button", "discussion_posted_ui")
        or prev.startswith("discussion_err")
        or prev.startswith("text_submitted")
        or prev.startswith("no_text_submit_button")
        or prev.startswith("text_submit_err")
        or prev.startswith("upload_")
    )
    if prev and not retriable:
        return prev
    title = item.get("title", "(untitled)")
    item_type = item.get("type", "")
    print(f"  [{item_type}] {title} (id={item['id']})", flush=True)
    out_dir = UNLOCKED / f"{item['id']}_{slug(title)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "item_meta.json").write_text(json.dumps(item, indent=2, default=str))
    result = "unknown"
    try:
        try:
            await page.goto(f"{BASE}/courses/{CID}/modules/items/{item['id']}",
                            wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass
        try:
            final_url = page.url
            (out_dir / "final_url.txt").write_text(final_url)
        except Exception:
            final_url = ""
        try:
            body_text = await page.inner_text("body", timeout=8000)
        except Exception:
            body_text = ""
        if "hasn't been unlocked" in body_text:
            result = "LOCKED"
        elif item_type == "Page":
            result = await process_page_item(page, out_dir)
        elif item_type == "Assignment":
            if item.get("quiz_lti"):
                result = await process_quiz_lti(page, item, out_dir, state, module_name)
            elif "/taking/" in final_url:
                result = await process_quiz_item(page, out_dir)
            elif "Submitting an external tool" in body_text or "external_tool" in body_text.lower():
                result = await process_h5p_assignment(page, out_dir)
            else:
                result = await process_assignment_text(page, item, out_dir)
        elif item_type == "Quiz":
            result = await process_quiz_item(page, out_dir)
        elif item_type == "Discussion":
            result = await process_discussion_item(page, item, out_dir)
        elif item_type in ("File", "ExternalUrl", "ExternalTool"):
            await safe_content(page, out_dir, "content")
            result = f"{item_type}_visited"
        else:
            result = f"skipped_type_{item_type}"
    except Exception as e:
        (out_dir / "fatal.error").write_text(traceback.format_exc())
        result = f"FATAL:{type(e).__name__}:{e}"
    state["done"][key] = result
    save_state(state)
    print(f"    -> {result}", flush=True)
    return result

def pending_terminal(result):
    """A result is 'terminal' (no further retry needed) when it isn't LOCKED, a transient error, or a failed quiz."""
    if not result:
        return False
    if result.startswith("LOCKED"):
        return False
    if result.startswith("quiz_lti_failed"):
        return False
    if result.startswith("FATAL"):
        return False
    if result.startswith("begin_err") or result.startswith("submit_err"):
        return False
    return True

async def main():
    only_mod = int(os.environ.get("ONLY_MODULE") or "0")
    stop_at  = int(os.environ.get("STOP_AT") or "0")
    state = load_state()
    print(f"Output root: {ROOT}", flush=True)
    print(f"Previous completions: {len(state['done'])}", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 2000})
        page = await ctx.new_page()
        print("Logging in...", flush=True)
        await login(page)

        last_locked = None
        for pass_num in range(1, MAX_PASSES + 1):
            print(f"\n######## PASS {pass_num}/{MAX_PASSES} ########", flush=True)
            print("Fetching modules...", flush=True)
            modules = await get_modules(page)
            modules.sort(key=lambda m: m.get("position", 0))
            pass_count = 0
            for m in modules:
                if only_mod and m["id"] != only_mod:
                    continue
                mname = m.get("name", f"module_{m['id']}")
                print(f"\n## Module {m.get('position')}: {mname} (id={m['id']})", flush=True)
                for it in (m.get("items") or []):
                    await process_item(page, it, state, module_name=mname)
                    pass_count += 1
                    if stop_at and pass_count >= stop_at:
                        print(f"\nReached STOP_AT={stop_at}, exiting pass.", flush=True)
                        break
                    await asyncio.sleep(1)
                if stop_at and pass_count >= stop_at:
                    break
            locked_now = sum(1 for v in state["done"].values() if v.startswith("LOCKED"))
            terminal_now = sum(1 for v in state["done"].values() if pending_terminal(v))
            print(f"\n=== After pass {pass_num}: terminal={terminal_now}, LOCKED={locked_now} ===", flush=True)
            if last_locked is not None and locked_now >= last_locked:
                print("No new unlocks this pass; stopping.", flush=True)
                break
            last_locked = locked_now
        await browser.close()
    print("\nDone.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
