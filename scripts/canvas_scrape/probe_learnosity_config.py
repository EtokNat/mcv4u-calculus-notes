"""Probe v3: capture Learnosity item config + runtime state during FC A load.

Three strategies in a single run:

  A) Network interception — register page.on("response") BEFORE Begin is clicked,
     capture every response whose URL contains learnosity/items/quiz/question.
     Save url + status + body (truncated). The item-config response typically
     contains `validation.valid_response.value` = the correct answer verbatim.

  B) DOM introspection — for each text input, walk up the parent chain capturing
     data-* attributes, class names, aria-label, placeholder, and check for
     sibling hidden inputs or math-editor wrappers (MathQuill, MathLive).

  C) JS runtime — evaluate `window.LearnosityItems`, `window.LearnosityApp`,
     and any variants; serialize whatever we can reach (getQuestions, getItems,
     validation methods) and save.

Target: FC A (assignment 14502) in course 616. Output: ./probe3/.
Dumps all key findings to stdout for log-grep readability.
"""
import os, json, pathlib, asyncio, re
from playwright.async_api import async_playwright

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"
AID  = 14502
OUT  = pathlib.Path(os.environ.get("OUT_ROOT", "./probe3")).resolve()
OUT.mkdir(parents=True, exist_ok=True)

LEARNOSITY_URL_PATTERNS = [
    "learnosity",
    "items.learnosity",
    "/items/",
    "/questions",
    "/quiz/",
    "quizzes.cognosonline",
    "newquizzes",
    "quiz-api",
]

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

def is_interesting(url):
    u = url.lower()
    return any(p in u for p in LEARNOSITY_URL_PATTERNS)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 2400})
        page = await ctx.new_page()

        # --- Strategy A setup: network response capture ---
        captured = []  # list of {url, status, body, headers, ct, is_json, valid_response_hits}

        async def handle_response(resp):
            try:
                url = resp.url
                if not is_interesting(url):
                    return
                ct = resp.headers.get("content-type", "")
                try:
                    body = await resp.body()
                    text = body.decode("utf-8", errors="replace")
                except Exception:
                    text = ""
                hits = []
                for key in ["valid_response", "validation", "correct_response", "scoring_data",
                            "score_data", "answer_key", "correct_answer", "is_correct"]:
                    if key in text:
                        hits.append(key)
                captured.append({
                    "url": url,
                    "status": resp.status,
                    "ct": ct,
                    "body_len": len(text),
                    "body_preview": text[:8000],
                    "valid_response_hits": hits,
                })
            except Exception as e:
                captured.append({"url": getattr(resp, "url", "?"), "error": str(e)})

        page.on("response", handle_response)

        # --- Login + launch ---
        print("[probe3] logging in", flush=True)
        await login(page)

        print("[probe3] navigating to launch URL", flush=True)
        await page.goto(f"{BASE}/courses/{CID}/assignments/{AID}/launch",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)

        print("[probe3] clicking Begin/Resume", flush=True)
        try:
            await page.locator('[data-automation="sdk-start-resume-button"]').first.click(timeout=15000)
        except Exception:
            try:
                await page.get_by_role("button", name=re.compile("Begin|Resume|Start|Take", re.I)).first.click(timeout=8000)
            except Exception as e:
                print(f"[probe3] start-click err: {e}", flush=True)

        try:
            await page.wait_for_selector('[data-automation="sdk-item-wrapper"]', timeout=45000)
        except Exception as e:
            print(f"[probe3] no items appeared: {e}", flush=True)

        await page.wait_for_timeout(8000)  # let all config responses land

        # Dump all captured network responses
        (OUT / "A_captured_responses.json").write_text(json.dumps(captured, indent=2))
        print(f"\n[probe3] === STRATEGY A: {len(captured)} responses captured ===", flush=True)
        interesting = [c for c in captured if c.get("valid_response_hits")]
        print(f"[probe3] Responses with validation-related keys: {len(interesting)}", flush=True)
        for c in interesting[:20]:
            print(f"  {c['url'][:150]}", flush=True)
            print(f"    status={c.get('status')} hits={c.get('valid_response_hits')} len={c.get('body_len')}", flush=True)
            # print snippet around first hit
            for key in c.get("valid_response_hits", []):
                body = c.get("body_preview", "")
                idx = body.find(key)
                if idx >= 0:
                    print(f"    [{key}] context: {body[max(0,idx-100):idx+300]!r}", flush=True)
                    break

        # If no explicit valid_response hits, still print top 10 responses so we can eyeball
        if not interesting:
            print("[probe3] No validation keys found; showing all captured URLs:", flush=True)
            for c in captured[:40]:
                print(f"  status={c.get('status')} len={c.get('body_len',0):6d} {c.get('url','?')[:180]}", flush=True)

        # --- Strategy B: DOM introspection across all frames ---
        print(f"\n[probe3] === STRATEGY B: DOM wrapper inspection ===", flush=True)
        for f in page.frames:
            if not f.url or 'learnosity' not in (f.url or '').lower() and 'quiz' not in (f.url or '').lower():
                # Also include empty-name iframes
                pass
            tag = (f.name or f.url or 'anon').replace('/', '_').replace(':', '_')[:60]
            try:
                dom_dump = await f.evaluate("""() => {
                    const result = {
                        url: location.href,
                        inputs: [],
                        math_wrappers: [],
                        hidden_inputs: [],
                    };
                    const txt_inputs = Array.from(document.querySelectorAll('input[type="text"], input[type="number"], input:not([type]), textarea'));
                    for (const inp of txt_inputs.slice(0, 50)) {
                        const walk = [];
                        let el = inp;
                        for (let i = 0; i < 8 && el; i++) {
                            walk.push({
                                tag: el.tagName,
                                id: el.id || null,
                                cls: (el.className || '').toString().slice(0, 200),
                                data_attrs: Object.fromEntries(
                                    Array.from(el.attributes || [])
                                        .filter(a => a.name.startsWith('data-'))
                                        .map(a => [a.name, a.value.slice(0, 200)])
                                ),
                                aria_label: el.getAttribute?.('aria-label') || null,
                                placeholder: el.getAttribute?.('placeholder') || null,
                            });
                            el = el.parentElement;
                        }
                        result.inputs.push({
                            id: inp.id,
                            type: inp.type,
                            value: inp.value,
                            classes: inp.className,
                            walk_up: walk,
                        });
                    }
                    // Hunt for math-editor markers
                    const math_sel = ['.mq-editable-field', '.mq-root-block', 'math-field',
                                      '[data-type*="formulaV2"]', '[data-type*="formula"]',
                                      '.mathquill-wrapper', '.lrn_math', '.lrn_formulaV2',
                                      '.lrn_cloze_formula'];
                    for (const sel of math_sel) {
                        const els = document.querySelectorAll(sel);
                        if (els.length > 0) {
                            result.math_wrappers.push({
                                selector: sel,
                                count: els.length,
                                first_outer: els[0].outerHTML?.slice(0, 2000),
                                first_latex: els[0].getAttribute?.('data-latex') || els[0].innerText?.slice(0, 500),
                            });
                        }
                    }
                    // Hidden inputs that may hold normalized LaTeX/MathML
                    const hidden = Array.from(document.querySelectorAll('input[type="hidden"]'));
                    for (const h of hidden.slice(0, 30)) {
                        if ((h.value || '').length > 0) {
                            result.hidden_inputs.push({
                                name: h.name, id: h.id, value: h.value.slice(0, 500),
                            });
                        }
                    }
                    return result;
                }""")
                (OUT / f"B_dom_{tag}.json").write_text(json.dumps(dom_dump, indent=2))
                print(f"\n[probe3] frame: {f.url[:120]}", flush=True)
                print(f"  inputs: {len(dom_dump.get('inputs', []))}", flush=True)
                print(f"  math_wrappers: {len(dom_dump.get('math_wrappers', []))}", flush=True)
                for mw in dom_dump.get('math_wrappers', [])[:5]:
                    print(f"    {mw['selector']}: count={mw['count']} latex={mw.get('first_latex','')[:200]!r}", flush=True)
                for inp in dom_dump.get('inputs', [])[:3]:
                    print(f"  input id={inp['id']} classes={inp['classes'][:80]}", flush=True)
                    for w in inp.get('walk_up', [])[:4]:
                        if w.get('data_attrs') or w.get('placeholder') or 'lrn' in (w.get('cls') or '').lower() or 'math' in (w.get('cls') or '').lower():
                            print(f"    walk[{w['tag']}]: cls={w['cls'][:100]} data={w['data_attrs']} ph={w.get('placeholder')!r}", flush=True)
                for h in dom_dump.get('hidden_inputs', [])[:10]:
                    print(f"  hidden: name={h.get('name')} val={h.get('value','')[:200]!r}", flush=True)
            except Exception as e:
                print(f"[probe3] frame {tag} dom err: {e}", flush=True)

        # --- Strategy C: JS runtime globals ---
        print(f"\n[probe3] === STRATEGY C: JS runtime introspection ===", flush=True)
        for f in page.frames:
            tag = (f.name or f.url or 'anon').replace('/', '_').replace(':', '_')[:60]
            try:
                js_dump = await f.evaluate("""() => {
                    const out = { globals_found: [], probes: {} };
                    const candidates = [
                        'LearnosityItems', 'LearnosityApp', 'LearnosityAssess', 'Learnosity',
                        '__learnosity', '_learnosity',
                        'itemsApp', 'items_app', 'activity', 'session',
                    ];
                    for (const g of candidates) {
                        try {
                            if (window[g] !== undefined) {
                                out.globals_found.push(g);
                                const obj = window[g];
                                const probe = {};
                                if (obj && typeof obj.getQuestions === 'function') {
                                    try {
                                        const qs = obj.getQuestions();
                                        probe.getQuestions_keys = Object.keys(qs || {}).slice(0, 20);
                                        probe.getQuestions_first = JSON.stringify(Object.values(qs || {})[0] || null).slice(0, 2000);
                                    } catch (e) { probe.getQuestions_err = String(e); }
                                }
                                if (obj && typeof obj.getItems === 'function') {
                                    try {
                                        const its = obj.getItems();
                                        probe.getItems_keys = Object.keys(its || {}).slice(0, 20);
                                        probe.getItems_first = JSON.stringify(Object.values(its || {})[0] || null).slice(0, 2000);
                                    } catch (e) { probe.getItems_err = String(e); }
                                }
                                if (obj && typeof obj.getScores === 'function') {
                                    try { probe.scores = JSON.stringify(obj.getScores() || null).slice(0, 2000); }
                                    catch (e) { probe.scores_err = String(e); }
                                }
                                probe.methods = Object.getOwnPropertyNames(Object.getPrototypeOf(obj || {})).slice(0, 50);
                                out.probes[g] = probe;
                            }
                        } catch (e) {}
                    }
                    // Scan all window props for learnosity-looking stuff
                    const all = Object.keys(window);
                    out.window_learnosity_keys = all.filter(k => /learnosity|items|quiz|assess/i.test(k)).slice(0, 50);
                    return out;
                }""")
                if js_dump.get('globals_found') or js_dump.get('window_learnosity_keys'):
                    (OUT / f"C_js_{tag}.json").write_text(json.dumps(js_dump, indent=2))
                    print(f"\n[probe3] frame: {f.url[:120]}", flush=True)
                    print(f"  globals_found: {js_dump.get('globals_found')}", flush=True)
                    print(f"  window keys: {js_dump.get('window_learnosity_keys')}", flush=True)
                    for g, probe in (js_dump.get('probes') or {}).items():
                        print(f"  [{g}] methods: {probe.get('methods')}", flush=True)
                        if probe.get('getQuestions_first'):
                            print(f"    getQuestions_first: {probe['getQuestions_first'][:800]!r}", flush=True)
                        if probe.get('scores'):
                            print(f"    scores: {probe['scores'][:500]!r}", flush=True)
            except Exception as e:
                pass

        # Screenshot to show what the rendered inputs look like
        try:
            await page.screenshot(path=str(OUT / "page_full.png"), full_page=True)
        except Exception:
            pass

        await browser.close()
    print("\n[probe3] DONE", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
