"""Probe: does loading the Canvas sessionless_launch URL for an H5P assignment
create a submission record on its own (without video playback)?

If yes: we iterate every Interactive Video Check, hit launch, move on.
If no: the only remaining paths are real video playback or teacher-role creds.
"""
import os, json, pathlib, asyncio
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"
AID  = 17404
OUT  = pathlib.Path(os.environ.get("OUT_ROOT", "./lti_probe")).resolve()
OUT.mkdir(parents=True, exist_ok=True)

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def submission_state(page):
    r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/assignments/{AID}/submissions/self")
    try:
        return r.status, await r.json()
    except Exception:
        return r.status, (await r.text())[:500]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 2000})
        page = await ctx.new_page()
        await login(page)

        # 1) submission state BEFORE
        s, body = await submission_state(page)
        (OUT / "submission_before.json").write_text(json.dumps({"status": s, "body": body}, indent=2, default=str))
        print(f"BEFORE: HTTP {s}, workflow_state={body.get('workflow_state') if isinstance(body, dict) else body}", flush=True)

        # 2) Fetch sessionless_launch URL
        r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/external_tools/sessionless_launch?assignment_id={AID}&launch_type=assessment")
        launch = await r.json()
        (OUT / "sessionless_launch.json").write_text(json.dumps(launch, indent=2, default=str))
        launch_url = launch.get("url")
        print(f"launch_url: {launch_url}", flush=True)

        if not launch_url:
            print("no launch URL returned, aborting", flush=True)
            await browser.close()
            return

        # 3) Visit the launch URL — loads H5P iframe, triggers LTI handshake
        try:
            await page.goto(launch_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(8000)
        except PWTimeout:
            print("goto timed out, continuing anyway", flush=True)

        try:
            (OUT / "launch_page.html").write_text(await page.content())
            (OUT / "launch_page.txt").write_text(await page.inner_text("body", timeout=5000))
        except Exception as e:
            (OUT / "launch_page.err").write_text(str(e))

        # Dump iframes seen
        frames = [{"name": f.name, "url": f.url} for f in page.frames]
        (OUT / "frames.json").write_text(json.dumps(frames, indent=2))
        print(f"frames: {len(frames)}", flush=True)
        for f in frames:
            print(f"  {f['name'] or '(main)':30s} {f['url']}", flush=True)

        # 4) Also try the assignment page itself — sometimes loads the iframe in context
        await page.goto(f"{BASE}/courses/{CID}/assignments/{AID}",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)
        try:
            (OUT / "assignment_page.html").write_text(await page.content())
            (OUT / "assignment_page.txt").write_text(await page.inner_text("body", timeout=5000))
            await page.screenshot(path=str(OUT / "assignment_page.png"), full_page=True, timeout=10000)
        except Exception as e:
            (OUT / "assignment_page.err").write_text(str(e))

        frames2 = [{"name": f.name, "url": f.url} for f in page.frames]
        (OUT / "assignment_frames.json").write_text(json.dumps(frames2, indent=2))

        # Wait a while longer for H5P to boot inside the iframe
        await page.wait_for_timeout(10000)

        # 5) submission state AFTER
        s2, body2 = await submission_state(page)
        (OUT / "submission_after.json").write_text(json.dumps({"status": s2, "body": body2}, indent=2, default=str))
        print(f"AFTER: HTTP {s2}, workflow_state={body2.get('workflow_state') if isinstance(body2, dict) else body2}", flush=True)
        if isinstance(body, dict) and isinstance(body2, dict):
            print(f"  attempt before={body.get('attempt')} after={body2.get('attempt')}", flush=True)
            print(f"  submitted_at before={body.get('submitted_at')} after={body2.get('submitted_at')}", flush=True)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
