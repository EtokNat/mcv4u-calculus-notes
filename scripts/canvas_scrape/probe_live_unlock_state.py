"""Probe: login + dump current unlock state from Canvas modules API.

For each module (unit), list every item with its lock status. Print to stdout
for log-grep so we can see the live picture without artifact download.
"""
import os, json, asyncio
from playwright.async_api import async_playwright

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        print("[live] logging in...", flush=True)
        await login(page)
        print("[live] login OK; fetching modules", flush=True)

        # Get all modules with items
        all_modules = []
        url = f"{BASE}/api/v1/courses/{CID}/modules?include[]=items&include[]=content_details&per_page=100"
        while url:
            r = await page.request.get(url)
            data = await r.json()
            if isinstance(data, list):
                all_modules.extend(data)
            link = r.headers.get("link", "")
            nxt = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    nxt = part.split(";")[0].strip().strip("<>")
                    break
            url = nxt

        total_units = 0
        total_items = 0
        fully_unlocked_units = []
        partially_unlocked_units = []
        fully_locked_units = []

        for m in all_modules:
            total_units += 1
            items = m.get("items") or []
            mod_name = m.get("name", "?")
            mod_state = m.get("state", "?")

            unlocked_count = 0
            locked_count = 0
            items_by_lock = []
            for it in items:
                total_items += 1
                cd = it.get("content_details") or {}
                locked = cd.get("locked_for_user")
                title = it.get("title", "?")
                itype = it.get("type", "?")
                if locked is True:
                    locked_count += 1
                    items_by_lock.append(("LOCKED", itype, title))
                else:
                    unlocked_count += 1
                    items_by_lock.append(("open  ", itype, title))

            status = "FULL-UNLOCK" if locked_count == 0 else ("PARTIAL" if unlocked_count > 0 else "FULL-LOCK")
            print(f"\n=== [{status}] {mod_name!r} (state={mod_state}) — {unlocked_count}/{len(items)} unlocked ===", flush=True)
            for lock, itype, title in items_by_lock:
                print(f"  {lock}  [{itype:18s}] {title}", flush=True)

            if locked_count == 0 and unlocked_count > 0:
                fully_unlocked_units.append(mod_name)
            elif unlocked_count > 0:
                partially_unlocked_units.append((mod_name, unlocked_count, len(items)))
            else:
                fully_locked_units.append(mod_name)

        print(f"\n\n=== SUMMARY ===", flush=True)
        print(f"Total modules: {total_units}", flush=True)
        print(f"Total items:   {total_items}", flush=True)
        print(f"FULLY UNLOCKED units: {len(fully_unlocked_units)}", flush=True)
        for u in fully_unlocked_units:
            print(f"  - {u}", flush=True)
        print(f"PARTIALLY UNLOCKED units: {len(partially_unlocked_units)}", flush=True)
        for u, un, tot in partially_unlocked_units:
            print(f"  - {u}: {un}/{tot}", flush=True)
        print(f"FULLY LOCKED units: {len(fully_locked_units)}", flush=True)
        for u in fully_locked_units:
            print(f"  - {u}", flush=True)

        await browser.close()
    print("\n[live] DONE", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
