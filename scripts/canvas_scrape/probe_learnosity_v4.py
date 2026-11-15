"""Probe v4: deep LearnosityApp introspection + full POST capture + postMessage sniff.

Strategy A+: capture every request/response (GET and POST), not just URL matches.
  - For POSTs that look like item/scoring, save request body + response body.

Strategy C+: deep LearnosityApp dump. Call every method on the object; dump its
  Backbone collections (models, items, questions). Walk into private fields
  like _items, _questions, _activity if they exist.

Strategy D: install a postMessage listener inside every frame, record every
  message received for 30s, dump payloads.

Output: ./probe4/. Everything dumped to stdout for log-grep readability.
"""
import os, json, pathlib, asyncio, re
from playwright.async_api import async_playwright

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"
AID  = 14502
OUT  = pathlib.Path(os.environ.get("OUT_ROOT", "./probe4")).resolve()
OUT.mkdir(parents=True, exist_ok=True)

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 2400})
        page = await ctx.new_page()

        # --- Capture ALL requests/responses with POST bodies ---
        requests_seen = []
        async def handle_request(req):
            try:
                if req.method == "POST" and ("learnosity" in req.url or "quiz" in req.url or "items" in req.url):
                    body = ""
                    try:
                        body = req.post_data or ""
                    except Exception:
                        pass
                    requests_seen.append({
                        "url": req.url, "method": req.method,
                        "post_body": (body or "")[:50000],
                    })
            except Exception:
                pass
        page.on("request", handle_request)

        responses_seen = []
        async def handle_response(resp):
            try:
                url = resp.url
                if not any(p in url.lower() for p in ["learnosity", "quiz", "items", "instructure.com/api"]):
                    return
                try:
                    body = await resp.body()
                    text = body.decode("utf-8", errors="replace")
                except Exception:
                    text = ""
                # Only save if body contains anything interesting-looking
                keys = ["valid_response", "correct_response", "scoring_data", "correctAnswer",
                        "\"question\":", "\"stimulus\":", "\"type\":\"formulaV2\"",
                        "\"items\":", "\"activity\":"]
                hits = [k for k in keys if k in text]
                responses_seen.append({
                    "url": url, "status": resp.status,
                    "method": resp.request.method,
                    "body_len": len(text), "hits": hits,
                    "body_preview": text[:4000] if hits else text[:500],
                    "body_full": text if hits else None,
                })
            except Exception as e:
                pass
        page.on("response", handle_response)

        print("[probe4] logging in", flush=True)
        await login(page)

        # Install postMessage sniffer on the main window early
        await page.add_init_script("""
            window.__pm_events = [];
            window.addEventListener('message', e => {
                try {
                    let data = e.data;
                    if (typeof data !== 'string') data = JSON.stringify(data);
                    window.__pm_events.push({
                        origin: e.origin,
                        data: data.slice(0, 20000),
                        ts: Date.now(),
                    });
                    if (window.__pm_events.length > 500) window.__pm_events.shift();
                } catch (err) {}
            });
        """)

        print("[probe4] navigating to launch URL", flush=True)
        await page.goto(f"{BASE}/courses/{CID}/assignments/{AID}/launch",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(6000)

        print("[probe4] clicking Begin/Resume", flush=True)
        try:
            await page.locator('[data-automation="sdk-start-resume-button"]').first.click(timeout=15000)
        except Exception:
            try:
                await page.get_by_role("button", name=re.compile("Begin|Resume|Start|Take", re.I)).first.click(timeout=8000)
            except Exception as e:
                print(f"[probe4] start-click err: {e}", flush=True)

        try:
            await page.wait_for_selector('[data-automation="sdk-item-wrapper"]', timeout=45000)
            print("[probe4] items wrapper appeared", flush=True)
        except Exception as e:
            print(f"[probe4] no items: {e}", flush=True)

        await page.wait_for_timeout(12000)  # let everything settle

        # --- Dump requests/responses ---
        (OUT / "A_responses.json").write_text(json.dumps(
            [{k: v for k, v in r.items() if k != "body_full"} for r in responses_seen],
            indent=2))
        # Save full bodies separately for interesting responses
        for i, r in enumerate(responses_seen):
            if r.get("body_full"):
                (OUT / f"A_full_{i}.txt").write_text(r["body_full"][:5000000])
        (OUT / "A_requests_post.json").write_text(json.dumps(requests_seen, indent=2))

        print(f"\n[probe4] === NETWORK CAPTURE: {len(responses_seen)} responses, {len(requests_seen)} POSTs ===", flush=True)
        print(f"\n--- POST requests ---", flush=True)
        for req in requests_seen[:30]:
            print(f"  POST {req['url'][:180]}", flush=True)
            if req.get("post_body"):
                print(f"    body[:500]: {req['post_body'][:500]!r}", flush=True)

        print(f"\n--- Responses with 'interesting' keys ---", flush=True)
        for r in responses_seen:
            if r.get("hits"):
                print(f"\n  {r.get('method')} {r['url'][:160]}", flush=True)
                print(f"    status={r['status']} len={r['body_len']} hits={r['hits']}", flush=True)
                # For each hit, dump context
                body = r.get("body_full") or r.get("body_preview") or ""
                for needle in r["hits"][:5]:
                    pos = body.find(needle)
                    if pos >= 0:
                        ctx = body[max(0, pos-100):pos+600]
                        # skip obvious CSS hits
                        if "lrn_widget" in ctx or ".css" in r["url"]:
                            print(f"    [{needle}] (CSS false positive, skip)", flush=True)
                            continue
                        print(f"    [{needle}@{pos}] {ctx!r}", flush=True)

        # --- Deep LearnosityApp introspection ---
        print(f"\n[probe4] === DEEP LEARNOSITYAPP DUMP ===", flush=True)
        for f in page.frames:
            if 'bronston' not in (f.url or ''):
                continue
            tag = (f.name or f.url or 'anon').replace('/', '_').replace(':', '_')[:60]
            try:
                dump = await f.evaluate("""() => {
                    const out = {url: location.href, apps: {}};
                    for (const g of ['LearnosityApp', 'LearnosityAssess', 'LearnosityItems', 'ItemsApp', 'itemsApp']) {
                        if (window[g] === undefined) continue;
                        const obj = window[g];
                        const info = {type: typeof obj};
                        // Enumerate all properties (own + proto)
                        const proto_methods = [];
                        let cur = obj;
                        let depth = 0;
                        while (cur && depth < 5) {
                            const names = Object.getOwnPropertyNames(cur);
                            for (const n of names) {
                                if (typeof cur[n] === 'function' && !proto_methods.includes(n)) {
                                    proto_methods.push(n);
                                }
                            }
                            cur = Object.getPrototypeOf(cur);
                            depth++;
                        }
                        info.methods = proto_methods.slice(0, 100);
                        // Try calling every zero-arg looking method
                        info.method_results = {};
                        for (const m of proto_methods) {
                            try {
                                if (typeof obj[m] !== 'function') continue;
                                // Skip anything taking required args
                                if (obj[m].length > 0) continue;
                                if (/^(set|destroy|remove|clear|stop|hide|show|init|start|teardown|save|submit|validate|render|register|on|off|trigger|bind|unbind|listen)/i.test(m)) continue;
                                const r = obj[m]();
                                let serialized = '';
                                try {
                                    serialized = JSON.stringify(r);
                                } catch (e) { serialized = String(r).slice(0, 200); }
                                info.method_results[m] = (serialized || String(r)).slice(0, 3000);
                            } catch (e) {
                                info.method_results[m] = `[err: ${String(e).slice(0, 100)}]`;
                            }
                        }
                        // Own data props
                        const own = {};
                        for (const k of Object.getOwnPropertyNames(obj)) {
                            try {
                                const v = obj[k];
                                if (typeof v === 'function') continue;
                                let s = '';
                                try { s = JSON.stringify(v); } catch (e) { s = String(v); }
                                own[k] = (s || '').slice(0, 3000);
                            } catch (e) {}
                        }
                        info.own_props = own;
                        out.apps[g] = info;
                    }
                    return out;
                }""")
                (OUT / f"C_app_{tag}.json").write_text(json.dumps(dump, indent=2))
                for g, info in (dump.get("apps") or {}).items():
                    print(f"\n[probe4] [{g}] methods: {info.get('methods')}", flush=True)
                    print(f"[probe4] [{g}] own_props keys: {list((info.get('own_props') or {}).keys())}", flush=True)
                    for k, v in (info.get("own_props") or {}).items():
                        if v and v != 'undefined' and v != 'null' and v != '{}':
                            print(f"  own.{k} = {v[:800]!r}", flush=True)
                    for m, r in (info.get("method_results") or {}).items():
                        if r and not r.startswith("[err") and r not in ('undefined', 'null', '{}', '[]', '""'):
                            # Interesting if contains question-related keys
                            lo = r.lower()
                            if any(x in lo for x in ['question', 'response', 'answer', 'score', 'valid', 'activity', 'item']):
                                print(f"  method.{m}() = {r[:1500]!r}", flush=True)
            except Exception as e:
                print(f"[probe4] frame {tag} eval err: {e}", flush=True)

        # --- PostMessage events ---
        print(f"\n[probe4] === POSTMESSAGE EVENTS ===", flush=True)
        try:
            pm = await page.evaluate("() => window.__pm_events || []")
            (OUT / "D_postmessage.json").write_text(json.dumps(pm, indent=2))
            print(f"[probe4] captured {len(pm)} postMessage events", flush=True)
            for e in pm[:30]:
                d = e.get("data", "")
                if any(k in d for k in ["valid_response", "correct_answer", "question", "response", "score", "activity"]):
                    print(f"  origin={e.get('origin')} data[:500]: {d[:500]!r}", flush=True)
        except Exception as e:
            print(f"[probe4] pm dump err: {e}", flush=True)

        await browser.close()
    print("\n[probe4] DONE", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
