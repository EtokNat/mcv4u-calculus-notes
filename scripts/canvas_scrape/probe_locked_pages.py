"""Probe: is Canvas's module-lock enforced at the pages API level, or only in the
modules UI wrapper?

For each known-locked Unit 2+ page, hit:
  (1) /api/v1/courses/:cid/pages/:url_slug   (direct pages API)
  (2) /courses/:cid/pages/:url_slug          (HTML view)
  (3) /api/v1/courses/:cid/modules/:mid/items/:iid  (module item wrapper)

Print each response status + body-length + first 200 chars of body/html to stdout
so results are readable via `gh run view --log` without artifact download.
"""
import os, json, asyncio
from playwright.async_api import async_playwright

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"

# Known-locked items pulled from unlock_state scrape (modules API reports locked_for_user=true)
TARGETS = [
    # (item_id, module_id, page_url_slug, title)
    ("32399", "3178", "lesson-2-dot-5-the-quotient-rule",    "Lesson 2.5 Quotient Rule"),
    ("32400", "3178", "lesson-2-dot-6-the-chain-rule",       "Lesson 2.6 Chain Rule"),
    ("32417", "3179", "lesson-3-dot-1-second-derivatives-notation-and-computation", "Lesson 3.1 Second Derivatives"),
    ("32418", "3179", "lesson-3-dot-2-motion-on-a-line-velocity-and-acceleration",  "Lesson 3.2 Motion on a Line"),
    ("32420", "3179", "lesson-3-dot-3-absolute-maximum-and-minimum-values-on-an-interval", "Lesson 3.3 Abs Max/Min"),
    ("32421", "3179", "lesson-3-dot-4-optimization-in-action-area-volume-and-distance",    "Lesson 3.4 Optimization"),
]

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

def summarize(body):
    if not body:
        return "(empty)"
    s = body if isinstance(body, str) else json.dumps(body)
    return s[:250].replace("\n", " ")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        print("logging in...", flush=True)
        await login(page)

        # Also do a full page-list once to see how many pages API lists vs what's modules-locked
        print("\n=== STEP 0: full pages list via API ===", flush=True)
        r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/pages?per_page=100")
        try:
            all_pages = await r.json()
            print(f"status={r.status} count_first_page={len(all_pages)}", flush=True)
            # print titles + publish state
            for pg in all_pages[:40]:
                print(f"  - {pg.get('url')!r:60s} published={pg.get('published')} locked={pg.get('locked_for_user')}", flush=True)
        except Exception as e:
            print(f"err listing pages: {e}", flush=True)

        print("\n=== STEP 1: probe known-locked items ===", flush=True)
        for iid, mid, slug, title in TARGETS:
            print(f"\n--- {title} (item={iid}, module={mid}) ---", flush=True)

            # (1) Direct pages API
            url1 = f"{BASE}/api/v1/courses/{CID}/pages/{slug}"
            try:
                r = await page.request.get(url1)
                body = await r.text()
                try:
                    j = json.loads(body)
                    locked = j.get("locked_for_user") if isinstance(j, dict) else None
                    body_len = len(j.get("body") or "") if isinstance(j, dict) else 0
                    print(f"(1) API pages/{slug}: status={r.status} locked_for_user={locked} body_len={body_len}", flush=True)
                    if body_len > 0:
                        print(f"    body[:300]: {summarize(j.get('body'))[:300]!r}", flush=True)
                except Exception:
                    print(f"(1) API pages/{slug}: status={r.status} len={len(body)} snippet={summarize(body)!r}", flush=True)
            except Exception as e:
                print(f"(1) ERR: {e}", flush=True)

            # (2) HTML view
            url2 = f"{BASE}/courses/{CID}/pages/{slug}"
            try:
                r = await page.request.get(url2)
                body = await r.text()
                has_lock = "hasn&#39;t been unlocked" in body or "locked_for_user" in body or "module_prerequisites" in body
                has_content = "wiki_page" in body and len(body) > 5000
                print(f"(2) HTML pages/{slug}: status={r.status} len={len(body)} has_lock_msg={has_lock} has_wiki_body={has_content}", flush=True)
            except Exception as e:
                print(f"(2) ERR: {e}", flush=True)

            # (3) Module-items wrapper
            url3 = f"{BASE}/api/v1/courses/{CID}/modules/{mid}/items/{iid}"
            try:
                r = await page.request.get(url3)
                body = await r.text()
                try:
                    j = json.loads(body)
                    print(f"(3) modules/{mid}/items/{iid}: status={r.status} locked_for_user={j.get('content_details', {}).get('locked_for_user')}", flush=True)
                except Exception:
                    print(f"(3) modules/{mid}/items/{iid}: status={r.status}", flush=True)
            except Exception as e:
                print(f"(3) ERR: {e}", flush=True)

        print("\n=== STEP 2: files API probe (one locked file if any) ===", flush=True)
        r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/files?per_page=100")
        try:
            files = await r.json()
            print(f"files list status={r.status} count={len(files) if isinstance(files, list) else '?'}", flush=True)
            # print first 10
            for f in (files if isinstance(files, list) else [])[:10]:
                print(f"  file id={f.get('id')} display_name={f.get('display_name')!r} locked_for_user={f.get('locked_for_user')} url={f.get('url', '')[:100]}", flush=True)
        except Exception as e:
            print(f"files err: {e}", flush=True)

        await browser.close()
    print("\nDONE", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
