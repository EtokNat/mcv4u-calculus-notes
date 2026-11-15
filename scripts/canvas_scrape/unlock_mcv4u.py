"""MCV4U Canvas unlocker — walks every module, saves content, solves & submits quizzes to unlock all units.

Resumable: state file at ./mcv4u_scrape/unlock_state.json. Rerunning skips items already marked done.

Env vars required:
    BRONSTON_USER = giscounsellor02@gmail.com
    BRONSTON_PASS = (password)

Optional env vars:
    ONLY_MODULE           = canvas module id (int) to restrict to a single module
    STOP_AT               = stop after N items in this run
    OUT_ROOT              = override output root (default: ./mcv4u_scrape)
    CID                   = Canvas course id (default: 616)
    HEADLESS              = "0" to run with a display (needs xvfb), default "1"
    SAVE_SCREENSHOTS      = "1" to save full-page PNGs (default "0")
    RETRY_PER_QUIZ        = max attempts per min_score quiz (default "3")
    MAX_PASSES            = max unlock passes per run (default "6")
    CAPTURE_PASSED_QUIZZES= "1" to open already-passed quizzes just to dump session_items (default "0")
    SKIP_CR_COMPLETED     = "1" to skip items whose completion_requirement.completed is True if already saved locally (default "1")
"""
import os, re, sys, json, time, html, asyncio, pathlib, traceback
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
UNSOLVED_FILE = ROOT / "unsolved_dump.json"
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
SAVE_SCREENSHOTS = os.environ.get("SAVE_SCREENSHOTS", "0") == "1"
RETRY_PER_QUIZ = int(os.environ.get("RETRY_PER_QUIZ", "3"))
MAX_PASSES = int(os.environ.get("MAX_PASSES", "6"))
CAPTURE_PASSED_QUIZZES = os.environ.get("CAPTURE_PASSED_QUIZZES", "0") == "1"
SKIP_CR_COMPLETED = os.environ.get("SKIP_CR_COMPLETED", "1") == "1"


def slug(s):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', str(s))[:100]


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    txt = re.sub(r'<br\s*/?>', '\n', raw, flags=re.I)
    txt = re.sub(r'</p\s*>', '\n', txt, flags=re.I)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = html.unescape(txt)
    txt = re.sub(r'[ \t]+', ' ', txt)
    txt = re.sub(r'\n\s*\n+', '\n', txt)
    return txt.strip()


def load_state():
    if STATE_FILE.exists():
        s = json.loads(STATE_FILE.read_text())
        s.setdefault("bank_hashes", [])
        s.setdefault("quiz_scores", {})
        return s
    return {"done": {}, "errors": {}, "bank_hashes": [], "quiz_scores": {}}


def save_state(st):
    STATE_FILE.write_text(json.dumps(st, indent=2))


def record_unsolved(entry: dict):
    """Persist unsolved quiz questions in ROOT/unsolved_dump.json keyed by aid+prompt."""
    existing = {}
    if UNSOLVED_FILE.exists():
        try:
            existing = json.loads(UNSOLVED_FILE.read_text())
        except Exception:
            existing = {}
    key = f"{entry.get('aid')}::{entry.get('prompt', '')[:160]}"
    existing[key] = entry
    UNSOLVED_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


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
    """Save HTML + text (and optional screenshot), swallowing any errors."""
    try:
        (out_dir / f"{name}.html").write_text(await page.content())
    except Exception as e:
        (out_dir / f"{name}.html.error").write_text(str(e))
    try:
        (out_dir / f"{name}.txt").write_text(await page.inner_text("body", timeout=8000))
    except Exception as e:
        (out_dir / f"{name}.txt.error").write_text(str(e))
    if SAVE_SCREENSHOTS:
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
        r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/assignments/{aid}/submissions/self?include[]=submission_history")
        return await r.json()
    except Exception:
        return {}


def latest_attempt_score(sub):
    """Extract the MOST RECENT attempt's score from submission_history (not the running max)."""
    hist = sub.get("submission_history") or []
    if not hist:
        return None
    for entry in reversed(hist):
        sc = entry.get("score")
        if sc is not None:
            return sc
    return None


def parse_session_items(raw_items):
    """Normalize quiz-api session_items JSON into clean question metadata."""
    parsed = []
    if not isinstance(raw_items, list):
        return parsed
    for it in sorted(raw_items, key=lambda x: x.get("position", 0)):
        item = it.get("item") or {}
        itype = item.get("interaction_type") or {}
        slug_val = itype.get("slug") or "unknown"
        idata = item.get("interaction_data") or {}
        choices = []
        for c in (idata.get("choices") or []):
            choices.append({
                "id": c.get("id"),
                "position": c.get("position"),
                "text": strip_html(c.get("item_body") or ""),
                "html": c.get("item_body") or "",
            })
        blanks = idata.get("blanks") or []
        parsed.append({
            "position": it.get("position"),
            "quiz_entry_id": it.get("quiz_entry_id"),
            "item_id": item.get("id"),
            "points": it.get("points_possible"),
            "slug": slug_val,
            "prompt_text": strip_html(item.get("item_body") or ""),
            "prompt_html": item.get("item_body") or "",
            "choices": choices,
            "num_blanks": len(blanks) if slug_val == "rich-fill-blank" else (1 if slug_val == "numeric" else 0),
            "interaction_data": idata,
        })
    return parsed


def write_bank(module_name, quiz_title, questions_meta, state, session_parsed=None):
    unit_dir = BANK / slug(module_name)
    unit_dir.mkdir(parents=True, exist_ok=True)
    f = unit_dir / f"{slug(quiz_title)}.md"
    existing = f.read_text() if f.exists() else f"# {quiz_title}\n\n**Unit:** {module_name}\n\n"
    new_blocks = []

    # Save ALL seen questions (solved or unsolved) to the question bank markdown
    source = session_parsed if session_parsed else questions_meta
    for q in source:
        prompt = (q.get("prompt_text") or q.get("prompt") or "").strip()
        if not prompt:
            continue
        h = str(hash(f"{quiz_title}::{prompt}"))
        if h in state["bank_hashes"]:
            continue
        state["bank_hashes"].append(h)
        new_blocks.append(q)

    if new_blocks:
        with f.open("w") as out:
            out.write(existing)
            for q in new_blocks:
                prompt = (q.get("prompt_text") or q.get("prompt") or "").strip()
                qslug = q.get("slug") or q.get("pattern") or "question"
                pts = q.get("points")
                hdr = f"## {qslug}" + (f" ({pts} pts)" if pts is not None else "")
                out.write(f"\n---\n\n{hdr}\n\n**Prompt:**\n\n```\n{prompt}\n```\n\n")
                choices = q.get("choices") or []
                if choices:
                    out.write("**Choices:**\n")
                    for c in choices:
                        out.write(f"- {c.get('text') or c}\n")
                    out.write("\n")
                ans = q.get("answers")
                if ans:
                    if isinstance(ans, list):
                        out.write("**Answers:** " + ", ".join(f"`{a}`" for a in ans) + "\n")
                    else:
                        out.write(f"**Answer:** `{json.dumps(ans, ensure_ascii=False)}`\n")


async def _fill_question_dom(page, wrapper_idx: int, q_dom: dict, res: dict, must_submit_only: bool, tag: str):
    """Fill a single New Quizzes question wrapper across all interaction types."""
    wrapper = page.locator('[data-automation="sdk-item-wrapper"]').nth(wrapper_idx)
    ans_type = res.get("type", "blanks") if res.get("ok") else None
    answers = res.get("answers") if res.get("ok") else None

    if res.get("ok"):
        if ans_type == "blanks" and isinstance(answers, list):
            inputs = wrapper.locator('input:not([type="radio"]):not([type="checkbox"]):not([type="hidden"]):not([type="submit"]):not([type="button"])')
            cnt = await inputs.count()
            for j, ans in enumerate(answers):
                if j >= cnt:
                    break
                try:
                    await inputs.nth(j).fill(str(ans), timeout=5000)
                except Exception as e:
                    print(f"      [{tag}] fill err q{wrapper_idx+1}[{j}]={ans}: {e}", flush=True)
            return True

        if ans_type == "choice" and isinstance(answers, dict):
            target = (answers.get("choice") or "").strip().lower()
            radios = q_dom.get("radios") or []
            for j, r_info in enumerate(radios):
                lbl = (r_info.get("label") or "").strip().lower()
                if target == lbl or target in lbl:
                    try:
                        await wrapper.locator('input[type="radio"]').nth(j).check(force=True, timeout=4000)
                        return True
                    except Exception:
                        try:
                            await wrapper.locator('input[type="radio"]').nth(j).click(force=True, timeout=4000)
                            return True
                        except Exception as e:
                            print(f"      [{tag}] radio err q{wrapper_idx+1}: {e}", flush=True)
            return False

        if ans_type == "multi" and isinstance(answers, dict):
            targets = [t.strip().lower() for t in (answers.get("choices") or [])]
            cbs = q_dom.get("checkboxes") or []
            matched = 0
            for j, cb_info in enumerate(cbs):
                lbl = (cb_info.get("label") or "").strip().lower()
                if any(t == lbl or t in lbl for t in targets):
                    try:
                        await wrapper.locator('input[type="checkbox"]').nth(j).check(force=True, timeout=4000)
                        matched += 1
                    except Exception as e:
                        print(f"      [{tag}] checkbox err q{wrapper_idx+1}: {e}", flush=True)
            return matched > 0

        if ans_type == "essay" and isinstance(answers, dict):
            txt = answers.get("text") or "Completed."
            return await _fill_essay_in_wrapper(page, wrapper, txt)

        if ans_type == "matching" and isinstance(answers, dict):
            pairs = answers.get("pairs") or {}
            selects = wrapper.locator("select")
            scnt = await selects.count()
            for j in range(scnt):
                sel = selects.nth(j)
                row_txt = (q_dom.get("selects") or [{}])[j].get("label", "").lower() if j < len(q_dom.get("selects") or []) else ""
                for k, v in pairs.items():
                    if k.lower() in row_txt:
                        try:
                            await sel.select_option(label=v, timeout=3000)
                        except Exception:
                            pass
            return True

    # Fallback for must_submit_only (Entry/Exit cards, 1-attempt Summatives): ensure every survey/essay has a valid selection
    if must_submit_only:
        if q_dom.get("radios"):
            try:
                await wrapper.locator('input[type="radio"]').first.check(force=True, timeout=3000)
            except Exception:
                pass
        if q_dom.get("has_essay"):
            await _fill_essay_in_wrapper(page, wrapper, "Completed for unit progression.")
    return False


async def _fill_essay_in_wrapper(page, wrapper, text: str) -> bool:
    try:
        ta = wrapper.locator("textarea:visible").first
        if await ta.count() > 0:
            await ta.fill(text, timeout=3000)
            return True
    except Exception:
        pass
    try:
        iframe = wrapper.locator(".tox-edit-area iframe, iframe").first
        if await iframe.count() > 0:
            fl = wrapper.frame_locator(".tox-edit-area iframe, iframe").first
            body = fl.locator("body#tinymce, body").first
            await body.click(timeout=3000)
            await page.keyboard.type(text[:500])
            return True
    except Exception:
        pass
    return False


async def _attempt_learnosity(page, aid, out_dir, tag, module_name="", quiz_title="", must_submit_only=False, capture_only=False):
    """Single attempt at a New Quiz. Captures session_items JSON, solves & submits."""
    captured_session_items = []

    async def on_response(resp):
        try:
            url = resp.url
            if "session_items" in url and resp.status == 200:
                data = await resp.json()
                if isinstance(data, list):
                    captured_session_items.clear()
                    captured_session_items.extend(data)
        except Exception:
            pass

    page.on("response", on_response)
    try:
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
        await page.wait_for_timeout(8000)
        try:
            await page.wait_for_selector('[data-automation="sdk-item-wrapper"]', timeout=30000)
        except Exception as e:
            print(f"    [{tag}] wait-items: {e}", flush=True)
            await safe_content(page, out_dir, f"no_items_{tag}")
            return None, [], []
        await page.wait_for_timeout(3000)

        if captured_session_items:
            (out_dir / f"session_items_{tag}.json").write_text(json.dumps(captured_session_items, indent=2))
        session_parsed = parse_session_items(captured_session_items)
        if session_parsed:
            (out_dir / f"questions_parsed_{tag}.json").write_text(json.dumps(session_parsed, indent=2, ensure_ascii=False))

        if capture_only:
            return None, [], session_parsed

        questions_dom = await page.evaluate("""() => {
            const wrappers = Array.from(document.querySelectorAll('[data-automation="sdk-item-wrapper"]'));
            const getLabel = (el) => {
                if (el.id) {
                    const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                    if (l && l.innerText) return l.innerText.trim();
                }
                const cl = el.closest('label');
                if (cl && cl.innerText) return cl.innerText.trim();
                return (el.parentElement?.innerText || '').trim();
            };
            return wrappers.map((w, i) => {
                const promptEl = w.querySelector('[data-automation="sdk-take-item-question"]');
                const textInputs = Array.from(w.querySelectorAll(
                    'input:not([type="radio"]):not([type="checkbox"]):not([type="hidden"]):not([type="submit"]):not([type="button"])'
                ));
                const radios = Array.from(w.querySelectorAll('input[type="radio"]')).map(el => ({
                    id: el.id, label: getLabel(el).slice(0, 500)
                }));
                const checkboxes = Array.from(w.querySelectorAll('input[type="checkbox"]')).map(el => ({
                    id: el.id, label: getLabel(el).slice(0, 500)
                }));
                const selects = Array.from(w.querySelectorAll('select')).map(el => ({
                    id: el.id, label: (el.closest('tr,div')?.innerText || '').slice(0, 300)
                }));
                const hasEssay = Boolean(w.querySelector('.tox-edit-area iframe, textarea'));
                return {
                    idx: i,
                    prompt: (promptEl?.innerText || w.innerText || '').slice(0, 4000),
                    num_text_inputs: textInputs.length,
                    input_ids: textInputs.map(el => el.id),
                    radios,
                    checkboxes,
                    selects,
                    has_essay: hasEssay,
                };
            });
        }""")
        print(f"    [{tag}] {len(questions_dom)} questions (session_items={len(session_parsed)})", flush=True)

        meta = []
        for idx, q in enumerate(questions_dom):
            sp = session_parsed[idx] if idx < len(session_parsed) else {}
            q_slug = sp.get("slug")
            prompt_for_solve = sp.get("prompt_text") or q["prompt"]
            n_inputs = q["num_text_inputs"]
            res = solve_question(prompt_for_solve, n_inputs, slug=q_slug)
            if not res.get("ok") and prompt_for_solve != q["prompt"]:
                res = solve_question(q["prompt"], n_inputs, slug=q_slug)
            filled_ok = await _fill_question_dom(page, idx, q, res, must_submit_only, tag)
            q_choices = sp.get("choices") or [r["label"] for r in (q.get("radios") or q.get("checkboxes") or [])]
            q_entry = {
                "idx": q["idx"],
                "slug": q_slug,
                "points": sp.get("points"),
                "prompt": prompt_for_solve,
                "prompt_dom": q["prompt"],
                "num_blanks": n_inputs,
                "choices": q_choices,
                "pattern": res.get("pattern"),
                "ok": bool(res.get("ok")),
                "answers": res.get("answers"),
                "reason": res.get("reason"),
                "filled": filled_ok,
            }
            meta.append(q_entry)
            if idx < len(session_parsed) and res.get("ok"):
                session_parsed[idx]["answers"] = res.get("answers")

            if not res.get("ok") and q_slug != "essay" and not q.get("has_essay") and not must_submit_only:
                print(f"      [UNSOLVED_Q] aid={aid} q={idx+1} slug={q_slug} blanks={n_inputs} | {prompt_for_solve[:260]!r}", flush=True)
                if q_choices:
                    print(f"        choices: {[c.get('text') if isinstance(c, dict) else c for c in q_choices]}", flush=True)
                record_unsolved({
                    "aid": aid,
                    "module": module_name,
                    "quiz": quiz_title,
                    "slug": q_slug,
                    "num_blanks": n_inputs,
                    "prompt": prompt_for_solve,
                    "choices": [c.get("text") if isinstance(c, dict) else c for c in q_choices],
                })

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
        best = None
        this_attempt = None
        for _ in range(8):
            await page.wait_for_timeout(3000)
            s = await submission_state(page, aid)
            sc = s.get("score")
            if s.get("submitted_at") is not None:
                best = sc
                this_attempt = latest_attempt_score(s)
                if sc is not None or must_submit_only:
                    break
        print(f"    [{tag}] this_attempt_score={this_attempt} running_max={best}", flush=True)
        for q in meta:
            q["this_attempt_score"] = this_attempt
        return best, meta, session_parsed
    finally:
        page.remove_listener("response", on_response)


async def capture_results_view(page, aid, out_dir, tag="results"):
    """Open an already-submitted quiz's launch/results view and save HTML + text."""
    try:
        await page.goto(f"{BASE}/courses/{CID}/assignments/{aid}/launch",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(6000)
        await safe_content(page, out_dir, tag)
        texts = []
        txt_p = out_dir / f"{tag}.txt"
        if txt_p.exists():
            texts.append(txt_p.read_text())
        for idx, fr in enumerate(page.frames[1:], 1):
            try:
                ft = await fr.inner_text("body", timeout=3000)
                if ft and ft.strip():
                    (out_dir / f"{tag}_frame{idx}.txt").write_text(ft)
                    texts.append(ft)
            except Exception:
                pass
        combined = "\n".join(texts)
        lines = [l.strip() for l in combined.splitlines() if l.strip()]
        diag = [l for l in lines if any(w in l.lower() for w in ("score", "point", "correct", "incorrect", "attempt", "question ", "waiting"))]
        if diag:
            print(f"    [RESULTS_DIAG aid={aid}] " + " | ".join(diag[:24])[:900], flush=True)
    except Exception as e:
        (out_dir / f"{tag}.error").write_text(str(e))


async def process_quiz_lti(page, item, out_dir, state, module_name):
    """New-Quiz (Learnosity / Quiz-API) item: handles both must_submit and min_score."""
    aid_m = re.search(r'/assignments/(\d+)', item.get("url", "") or "")
    if not aid_m:
        return "quiz_lti_no_aid"
    aid = int(aid_m.group(1))
    cr = item.get("completion_requirement") or {}
    req_type = cr.get("type")
    cr_completed = bool(cr.get("completed"))
    is_min_score = (req_type == "min_score")
    min_score = float(cr.get("min_score") or 60.0) if is_min_score else None
    title = item.get("title", f"quiz_{aid}")
    (out_dir / "quiz_lti.json").write_text(json.dumps({"aid": aid, "req_type": req_type, "min_score": min_score}, indent=2))

    s = await submission_state(page, aid)

    # --- Case 1: must_submit (Entry/Exit cards, 1-attempt Summatives) ---
    if not is_min_score:
        if s.get("submitted_at") is not None or cr_completed:
            if not (out_dir / "results.txt").exists():
                await capture_results_view(page, aid, out_dir)
            state["quiz_scores"][str(item["id"])] = s.get("score")
            return f"quiz_lti_already_submitted:{s.get('score')}"
        try:
            score, meta, sp = await _attempt_learnosity(
                page, aid, out_dir, f"{item['id']}#r1",
                module_name=module_name, quiz_title=title, must_submit_only=True
            )
            write_bank(module_name, title, meta, state, session_parsed=sp)
            (out_dir / "attempts_meta.json").write_text(json.dumps(meta, indent=2, default=str))
            await capture_results_view(page, aid, out_dir)
            state["quiz_scores"][str(item["id"])] = score
            return f"quiz_lti_submitted:{score}"
        except Exception as e:
            print(f"    must_submit exc: {e}", flush=True)
            return f"quiz_lti_submit_err:{e}"

    # --- Case 2: min_score (Formative Checks) ---
    if (s.get("score") is not None and float(s["score"]) >= min_score) or cr_completed:
        state["quiz_scores"][str(item["id"])] = s.get("score")
        if CAPTURE_PASSED_QUIZZES and not list(out_dir.glob("session_items_*.json")):
            _, _, sp = await _attempt_learnosity(
                page, aid, out_dir, f"{item['id']}#cap",
                module_name=module_name, quiz_title=title, capture_only=True
            )
            write_bank(module_name, title, [], state, session_parsed=sp)
        return f"quiz_lti_already_passed:{s.get('score')}"

    best_score = float(s.get("score") or -1.0)
    best_meta = []
    for retry in range(1, RETRY_PER_QUIZ + 1):
        try:
            score, meta, sp = await _attempt_learnosity(
                page, aid, out_dir, f"{item['id']}#r{retry}",
                module_name=module_name, quiz_title=title, must_submit_only=False
            )
        except Exception as e:
            print(f"    attempt exc: {e}", flush=True)
            score, meta, sp = None, [], []
        if meta:
            best_meta = meta
        write_bank(module_name, title, meta, state, session_parsed=sp)
        if score is not None and float(score) > best_score:
            best_score = float(score)
        this_sc = meta[0].get("this_attempt_score") if meta else None
        print(f"    [r{retry}] this={this_sc} running_best={best_score}", flush=True)
        if (this_sc is not None and float(this_sc) >= min_score) or best_score >= min_score:
            break
        # If more than half of auto-graded questions are unsolved after 2 pool draws, stop burning retries
        auto_qs = [q for q in meta if q.get("slug") != "essay"]
        unsolved_qs = [q for q in auto_qs if not q.get("ok")]
        if retry >= 2 and auto_qs and len(unsolved_qs) > max(2, len(auto_qs) // 2):
            print(f"    [{item['id']}] {len(unsolved_qs)}/{len(auto_qs)} unsolved after 2 draws; stopping retries for answer bank update.", flush=True)
            break
    state["quiz_scores"][str(item["id"])] = best_score
    (out_dir / "attempts_meta.json").write_text(json.dumps(best_meta, indent=2, default=str))
    if best_score < min_score:
        await capture_results_view(page, aid, out_dir, tag=f"results_{item['id']}")
    return f"quiz_lti_passed:{best_score}" if best_score >= min_score else f"quiz_lti_failed:{best_score}"


async def process_quiz_item(page, out_dir):
    """Classic / fallback quiz handler."""
    try:
        begin = page.locator('button:has-text("Begin")')
        if await begin.count() > 0:
            await begin.first.click(timeout=10000)
            await page.wait_for_timeout(6000)
            await safe_content(page, out_dir, "questions")
        else:
            await safe_content(page, out_dir, "questions_no_begin")
    except Exception as e:
        (out_dir / "begin.error").write_text(traceback.format_exc())
        return f"begin_err:{e}"
    try:
        submit_btn = page.locator('button:has-text("Submit")')
        if await submit_btn.count() == 0:
            return "no_submit_button"
        await submit_btn.last.click(timeout=10000)
        await page.wait_for_timeout(2500)
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
    """H5P LTI external_tool assignment: dump H5PIntegration + trigger XAPI completion."""
    await safe_content(page, out_dir, "content")
    await page.wait_for_timeout(10000)
    launch_frame = None
    for f in page.frames:
        if "h5p.com" in (f.url or "") and "lti" in (f.url or ""):
            launch_frame = f
            break
    if not launch_frame:
        return "no_h5p_launch_frame"
    try:
        h5p_int = await launch_frame.evaluate(
            "() => (typeof H5PIntegration !== 'undefined') ? JSON.parse(JSON.stringify(H5PIntegration)) : null"
        )
        if h5p_int:
            (out_dir / "h5p_integration.json").write_text(json.dumps(h5p_int, indent=2, default=str))
    except Exception as e:
        (out_dir / "h5p_integration.error").write_text(str(e))
    content_frame = None
    for f in page.frames:
        if f.name and f.name.startswith("h5p-iframe-"):
            content_frame = f
            break
    if not content_frame:
        return "no_h5p_content_frame"
    for _ in range(6):
        ready = await content_frame.evaluate(
            "() => (typeof H5P !== 'undefined' && Array.isArray(H5P.instances) && H5P.instances.length > 0)"
        )
        if ready:
            break
        await page.wait_for_timeout(2000)
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
    await page.wait_for_timeout(5000)
    if trig.get("err"):
        return f"h5p_err:{trig.get('err')}"
    return f"h5p_triggered:{trig.get('lib')}"


async def _canvas_api_fetch(page, endpoint, method="POST", body=None, content_type="application/json", extra_headers=None):
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
    await safe_content(page, out_dir, "content")
    aid = item.get("content_id")
    if aid:
        txt = await _canvas_api_fetch(
            page,
            f"{BASE}/api/v1/courses/{CID}/assignments/{aid}/submissions",
            method="POST",
            body={"submission": {"submission_type": "online_text_entry", "body": "Submitted for completion."}},
        )
        (out_dir / "text_submit_api.json").write_text(json.dumps(txt, indent=2))
        if 200 <= (txt.get("status") or 0) < 300:
            return f"text_submit_api:{txt.get('status')}"
        upload_result = await submit_assignment_online_upload(page, aid, out_dir)
        if upload_result.startswith("assignment_api_submitted"):
            return upload_result
        (out_dir / "assignment_api.summary").write_text(f"text_entry: {txt.get('status')}\nupload: {upload_result}\n")
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


def _already_captured(out_dir: pathlib.Path, item_type: str, is_quiz_lti: bool) -> bool:
    if item_type == "Page":
        return (out_dir / "main.html").exists() or (out_dir / "content.txt").exists()
    if is_quiz_lti:
        return (
            list(out_dir.glob("session_items_*.json")) != []
            or (out_dir / "results.txt").exists()
            or (out_dir / "attempts_meta.json").exists()
        )
    if item_type == "Assignment":
        return (out_dir / "h5p_integration.json").exists() or (out_dir / "content.txt").exists()
    return (out_dir / "content.txt").exists()


async def process_item(page, item, state, module_name=""):
    """Walk one module item; skip if already terminal + captured, or if CR completed + captured."""
    key = str(item["id"])
    prev = state["done"].get(key, "")
    title = item.get("title", "(untitled)")
    item_type = item.get("type", "")
    out_dir = UNLOCKED / f"{item['id']}_{slug(title)}"
    cr = item.get("completion_requirement") or {}
    cr_completed = bool(cr.get("completed"))

    retriable = (
        prev.startswith("LOCKED")
        or prev.startswith("quiz_lti_failed")
        or prev.startswith("quiz_lti_submit_err")
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
    if prev and not retriable and not (CAPTURE_PASSED_QUIZZES and item.get("quiz_lti")):
        return prev
    if SKIP_CR_COMPLETED and cr_completed and _already_captured(out_dir, item_type, bool(item.get("quiz_lti"))):
        if not prev or prev.startswith("LOCKED"):
            state["done"][key] = "cr_completed_cached"
            save_state(state)
        return state["done"].get(key, "cr_completed_cached")
    if (item.get("content_details") or {}).get("locked_for_user"):
        if prev != "LOCKED":
            state["done"][key] = "LOCKED"
            save_state(state)
        return "LOCKED"

    print(f"  [{item_type}] {title} (id={item['id']})", flush=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "item_meta.json").write_text(json.dumps(item, indent=2, default=str))
    result = "unknown"
    try:
        try:
            await page.goto(f"{BASE}/courses/{CID}/modules/items/{item['id']}",
                            wait_until="domcontentloaded", timeout=30000)
            if item_type in ("Assignment", "Quiz"):
                await page.wait_for_load_state("networkidle", timeout=5000)
            else:
                await page.wait_for_timeout(400)
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
    if not result:
        return False
    if result.startswith("LOCKED"):
        return False
    if result.startswith("quiz_lti_failed") or result.startswith("quiz_lti_submit_err"):
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
            (ROOT / f"course_{CID}" / "modules_latest.json").write_text(json.dumps(modules, indent=2, default=str))
            pass_count = 0
            for m in modules:
                if only_mod and m["id"] != only_mod:
                    continue
                mname = m.get("name", f"module_{m['id']}")
                mstate = m.get("state")
                print(f"\n## Module {m.get('position')}: {mname} (id={m['id']}, state={mstate})", flush=True)
                if mstate == "locked":
                    changed = False
                    for it in (m.get("items") or []):
                        k = str(it["id"])
                        if not state["done"].get(k):
                            state["done"][k] = "LOCKED"
                            changed = True
                    if changed:
                        save_state(state)
                    print(f"  (module locked -- skipped {len(m.get('items') or [])} items)", flush=True)
                    continue
                for it in (m.get("items") or []):
                    await process_item(page, it, state, module_name=mname)
                    pass_count += 1
                    if stop_at and pass_count >= stop_at:
                        print(f"\nReached STOP_AT={stop_at}, exiting pass.", flush=True)
                        break
                    await asyncio.sleep(0.3)
                if stop_at and pass_count >= stop_at:
                    break
            locked_now = sum(1 for v in state["done"].values() if v.startswith("LOCKED"))
            terminal_now = sum(1 for v in state["done"].values() if pending_terminal(v))
            print(f"\n=== After pass {pass_num}: terminal={terminal_now}, LOCKED={locked_now} ===", flush=True)
            if locked_now == 0:
                print("All items unlocked!", flush=True)
                break
            if last_locked is not None and locked_now >= last_locked:
                print("No new unlocks this pass; stopping.", flush=True)
                break
            last_locked = locked_now
        await browser.close()
    print("\nDone.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
