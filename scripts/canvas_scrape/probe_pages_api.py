"""Probe: are /api/v1/courses/:id/pages and :/pages/:url readable even when the
containing module is locked?

If yes, we can pull every lesson Page body without bothering with the Interactive
Video Check progression gate at all.

Writes ./pages_probe/pages_index.json and per-page body dumps.
"""
import os, json, pathlib, asyncio
from playwright.async_api import async_playwright

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"
OUT  = pathlib.Path(os.environ.get("OUT_ROOT", "./pages_probe")).resolve()
OUT.mkdir(parents=True, exist_ok=True)

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

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await login(page)

        # 1) List all pages
        pages = await paginate(page, f"{BASE}/api/v1/courses/{CID}/pages?per_page=100")
        (OUT / "pages_index.json").write_text(json.dumps(pages, indent=2, default=str))
        print(f"found {len(pages)} pages via API", flush=True)

        # 2) Fetch each page body
        bodies_dir = OUT / "bodies"
        bodies_dir.mkdir(exist_ok=True)
        ok, fail = 0, 0
        for pg in pages:
            url_slug = pg.get("url")
            if not url_slug:
                continue
            r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/pages/{url_slug}")
            try:
                data = await r.json()
            except Exception:
                data = {"_status": r.status, "_body": (await r.text())[:500]}
            safe = url_slug.replace("/", "_")[:120]
            (bodies_dir / f"{safe}.json").write_text(json.dumps(data, indent=2, default=str))
            if r.status == 200 and data.get("body"):
                ok += 1
            else:
                fail += 1
        print(f"fetched bodies: {ok} with content, {fail} empty/err", flush=True)

        # 3) Also try assignments list - maybe we can pull assignment descriptions
        assignments = await paginate(page, f"{BASE}/api/v1/courses/{CID}/assignments?per_page=100")
        (OUT / "assignments_index.json").write_text(json.dumps(assignments, indent=2, default=str))
        print(f"found {len(assignments)} assignments via API", flush=True)

        # 4) Files list
        files = await paginate(page, f"{BASE}/api/v1/courses/{CID}/files?per_page=100")
        (OUT / "files_index.json").write_text(json.dumps(files, indent=2, default=str))
        print(f"found {len(files)} files via API", flush=True)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
