"""Scrape H5P iframe contents for every MCV4U assignment.

We can't satisfy Canvas's must_submit gate, but we CAN still load each assignment
page — the H5P iframe renders inline regardless of progression state. We capture:
  - the top-level Canvas page HTML/text/screenshot
  - every cross-origin iframe's URL, HTML (if accessible), text, and a screenshot

Resumable via ./h5p_frames/state.json. Env vars:
    BRONSTON_USER, BRONSTON_PASS (required)
    CID (default 616)
    OUT_ROOT (default ./h5p_frames)
    ONLY_ID  (restrict to one assignment id, for smoke-testing)
    STOP_AT  (stop after N items)
    FRAME_WAIT_MS (how long to wait for H5P boot, default 12000)
"""
import os, re, json, pathlib, asyncio, time
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = os.environ.get("CID", "616")
ROOT = pathlib.Path(os.environ.get("OUT_ROOT", "./h5p_frames")).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
STATE_FILE = ROOT / "state.json"
ONLY_ID = int(os.environ.get("ONLY_ID") or "0")
STOP_AT = int(os.environ.get("STOP_AT") or "0")
FRAME_WAIT_MS = int(os.environ.get("FRAME_WAIT_MS") or "12000")

def slug(s):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', str(s))[:100]

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"done": {}}

def save_state(st):
    STATE_FILE.write_text(json.dumps(st, indent=2))

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def paginate(page, url):
    out = []
    while url:
        r = await page.request.get(url)
        data = await r.json()
        if isinstance(data, list):
            out.extend(data)
        else:
            out.append(data)
        link = r.headers.get("link", "")
        nxt = None
        for part in link.split(","):
            if 'rel="next"' in part:
                nxt = part.split(";")[0].strip().strip("<>")
                break
        url = nxt
    return out

async def capture_frame(frame, out_dir, name):
    """Dump cross-origin iframe content: URL, HTML, text, media, H5PIntegration."""
    meta = {"name": frame.name, "url": frame.url}
    (out_dir / f"{name}.meta.json").write_text(json.dumps(meta, indent=2))
    try:
        html = await frame.content()
        (out_dir / f"{name}.html").write_text(html)
    except Exception as e:
        (out_dir / f"{name}.html.error").write_text(str(e))
    try:
        txt = await frame.locator("body").inner_text(timeout=4000)
        (out_dir / f"{name}.txt").write_text(txt)
    except Exception as e:
        (out_dir / f"{name}.txt.error").write_text(str(e))
    try:
        media = await frame.evaluate("""
            () => {
                const urls = [];
                document.querySelectorAll('img, video, source, iframe, audio, a[href]').forEach(el => {
                    const src = el.src || el.href || el.getAttribute('data-src');
                    if (src) urls.push({tag: el.tagName, src});
                });
                return urls;
            }
        """)
        (out_dir / f"{name}.media.json").write_text(json.dumps(media, indent=2))
    except Exception as e:
        (out_dir / f"{name}.media.error").write_text(str(e))
    # H5PIntegration — the content JSON with questions/answers/video metadata
    try:
        h5p_int = await frame.evaluate("""
            () => {
                if (typeof H5PIntegration === 'undefined') return null;
                try { return JSON.parse(JSON.stringify(H5PIntegration)); }
                catch(e) { return {_err: String(e)}; }
            }
        """)
        if h5p_int:
            (out_dir / f"{name}.h5pintegration.json").write_text(json.dumps(h5p_int, indent=2, default=str))
    except Exception as e:
        (out_dir / f"{name}.h5pintegration.error").write_text(str(e))
    # Pull every <script type="application/json"> payload (H5P often ships content.json inline)
    try:
        payloads = await frame.evaluate("""
            () => Array.from(document.querySelectorAll('script[type="application/json"], script[data-h5p]'))
                      .map(s => ({id: s.id, type: s.type, text: s.textContent.slice(0, 500000)}))
        """)
        if payloads:
            (out_dir / f"{name}.jsonscripts.json").write_text(json.dumps(payloads, indent=2))
    except Exception:
        pass

async def scrape_assignment(page, assn, state):
    key = str(assn["id"])
    if key in state["done"] and state["done"][key].startswith("ok"):
        return state["done"][key]
    title = assn.get("name", "(untitled)")
    out_dir = ROOT / f"{assn['id']}_{slug(title)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "assignment_meta.json").write_text(json.dumps(assn, indent=2, default=str))
    print(f"  [{assn['id']}] {title}", flush=True)
    result = "unknown"
    try:
        try:
            await page.goto(f"{BASE}/courses/{CID}/assignments/{assn['id']}",
                            wait_until="domcontentloaded", timeout=30000)
        except PWTimeout:
            pass
        # Let the H5P iframe boot (cross-origin network).
        await page.wait_for_timeout(FRAME_WAIT_MS)
        try:
            (out_dir / "canvas.html").write_text(await page.content())
        except Exception as e:
            (out_dir / "canvas.html.error").write_text(str(e))
        try:
            (out_dir / "canvas.txt").write_text(await page.inner_text("body", timeout=5000))
        except Exception as e:
            (out_dir / "canvas.txt.error").write_text(str(e))
        try:
            await page.screenshot(path=str(out_dir / "canvas.png"), full_page=True, timeout=15000)
        except Exception as e:
            (out_dir / "canvas.png.error").write_text(str(e))

        # Capture every frame
        frames = page.frames
        frame_meta = []
        for i, f in enumerate(frames):
            tag = f"frame_{i}"
            if "h5p.com" in (f.url or ""):
                tag = f"h5p_{i}"
            elif f == page.main_frame:
                continue  # already captured above
            await capture_frame(f, out_dir, tag)
            frame_meta.append({"tag": tag, "name": f.name, "url": f.url})
        (out_dir / "frames.json").write_text(json.dumps(frame_meta, indent=2))

        # If an H5P frame exists, try to click inside it to reveal answer UI
        h5p_frames = [f for f in frames if "h5p.com" in (f.url or "")]
        if h5p_frames:
            hf = h5p_frames[0]
            try:
                await hf.locator("body").click(timeout=3000)
                await page.wait_for_timeout(3000)
                await capture_frame(hf, out_dir, "h5p_after_click")
            except Exception:
                pass
            # Try to walk any "Next slide" / "Continue" buttons inside H5P
            for step in range(20):
                try:
                    btns = hf.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Check"), button[aria-label*="Next"], button[aria-label*="Continue"]')
                    n = await btns.count()
                    if n == 0:
                        break
                    await btns.first.click(timeout=2500)
                    await page.wait_for_timeout(1500)
                except Exception:
                    break
            await capture_frame(hf, out_dir, "h5p_final")
            try:
                await page.screenshot(path=str(out_dir / "canvas_final.png"), full_page=True, timeout=15000)
            except Exception:
                pass
            result = f"ok:h5p_frames={len(h5p_frames)}"
        else:
            result = "ok:no_h5p_frame"
    except Exception as e:
        (out_dir / "error.txt").write_text(f"{type(e).__name__}: {e}")
        result = f"ERR:{type(e).__name__}:{e}"
    state["done"][key] = result
    save_state(state)
    print(f"    -> {result}", flush=True)
    return result

async def main():
    state = load_state()
    print(f"Output root: {ROOT}", flush=True)
    print(f"Previous completions: {len(state['done'])}", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 2200})
        page = await ctx.new_page()
        print("Logging in...", flush=True)
        await login(page)
        print("Fetching assignments...", flush=True)
        assignments = await paginate(page, f"{BASE}/api/v1/courses/{CID}/assignments?per_page=100")
        (ROOT / "assignments_index.json").write_text(json.dumps(assignments, indent=2, default=str))
        print(f"found {len(assignments)} assignments", flush=True)
        # Prioritize H5P-backed ones
        assignments.sort(key=lambda a: (a.get("position") or 0, a.get("id")))
        count = 0
        for a in assignments:
            if ONLY_ID and a["id"] != ONLY_ID:
                continue
            await scrape_assignment(page, a, state)
            count += 1
            if STOP_AT and count >= STOP_AT:
                print(f"STOP_AT={STOP_AT} reached", flush=True)
                break
            await asyncio.sleep(1)
        await browser.close()
    print("Done.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
