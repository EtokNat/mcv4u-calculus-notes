"""Check what's unlocked in Unit 1 and the overall course module graph."""
import os, json, pathlib, asyncio
from playwright.async_api import async_playwright

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"
OUT  = pathlib.Path(os.environ.get("OUT_ROOT", "./unlock_check")).resolve()
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
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await login(page)

        # All modules
        r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/modules?per_page=50")
        modules = await r.json()
        (OUT / "modules.json").write_text(json.dumps(modules, indent=2, default=str))

        summary = []
        for m in modules:
            mid = m["id"]
            mstate = m.get("state")
            r2 = await page.request.get(f"{BASE}/api/v1/courses/{CID}/modules/{mid}/items?per_page=100&include[]=content_details")
            items = await r2.json()
            (OUT / f"module_{mid}_items.json").write_text(json.dumps(items, indent=2, default=str))
            locked = sum(1 for it in items if (it.get("content_details") or {}).get("locked_for_user"))
            total = len(items)
            unlocked = total - locked
            summary.append({"name": m["name"], "id": mid, "state": mstate,
                            "total": total, "unlocked": unlocked, "locked": locked})
            print(f"{m['name']}: {unlocked}/{total} unlocked (state={mstate})", flush=True)

        (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2, default=str))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
