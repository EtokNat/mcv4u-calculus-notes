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

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = os.environ.get("CID", "616")
ROOT = pathlib.Path(os.environ.get("OUT_ROOT", "./mcv4u_scrape")).resolve()
UNLOCKED = ROOT / f"course_{CID}" / "unlocked_items"
UNLOCKED.mkdir(parents=True, exist_ok=True)
STATE_FILE = ROOT / "unlock_state.json"
HEADLESS = os.environ.get("HEADLESS", "1") != "0"

def slug(s):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', str(s))[:100]

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"done": {}, "errors": {}}

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

async def process_assignment_text(page, out_dir):
    """Non-quiz assignment: try text entry submission."""
    await safe_content(page, out_dir, "content")
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

async def process_discussion_item(page, out_dir):
    await safe_content(page, out_dir, "content")
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
            return "discussion_posted"
        return "no_post_button"
    except Exception as e:
        (out_dir / "discussion.error").write_text(traceback.format_exc())
        return f"discussion_err:{e}"

async def process_item(page, item, state):
    """Hardened: any failure sets a state entry and never silently drops the loop."""
    key = str(item["id"])
    if key in state["done"] and not state["done"][key].startswith("LOCKED"):
        return state["done"][key]
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
            if "/taking/" in final_url:
                result = await process_quiz_item(page, out_dir)
            else:
                result = await process_assignment_text(page, out_dir)
        elif item_type == "Quiz":
            result = await process_quiz_item(page, out_dir)
        elif item_type == "Discussion":
            result = await process_discussion_item(page, out_dir)
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
        print("Fetching modules...", flush=True)
        modules = await get_modules(page)
        modules.sort(key=lambda m: m.get("position", 0))
        count = 0
        for m in modules:
            if only_mod and m["id"] != only_mod:
                continue
            print(f"\n## Module {m.get('position')}: {m.get('name')} (id={m['id']})", flush=True)
            for it in (m.get("items") or []):
                await process_item(page, it, state)
                count += 1
                if stop_at and count >= stop_at:
                    print(f"\nReached STOP_AT={stop_at}, exiting.", flush=True)
                    await browser.close()
                    return
                await asyncio.sleep(1)
        await browser.close()
    print("\nDone.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
