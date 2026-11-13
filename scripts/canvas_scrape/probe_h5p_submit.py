"""Probe: can we POST a Canvas submission that satisfies must_submit on an H5P LTI assignment?

Target: course 616 / assignment 17404 (Lesson 1.1 Interactive Video Check).

Tries a handful of submission_type values in order and stops at the first that returns
a 2xx AND flips the module item's completion_requirement.completed to true.

Output: ./h5p_probe/<timestamp>/attempt_<n>.json for every try, plus summary.json.
"""
import os, json, time, pathlib, asyncio
from playwright.async_api import async_playwright

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"
AID  = 17404   # assignment id
MID  = 41134   # module item id

OUT = pathlib.Path(os.environ.get("OUT_ROOT", "./h5p_probe")).resolve()
OUT.mkdir(parents=True, exist_ok=True)

ATTEMPTS = [
    {"name": "online_url",     "form": {"submission[submission_type]": "online_url",      "submission[url]": "https://example.com"}},
    {"name": "online_text",    "form": {"submission[submission_type]": "online_text_entry","submission[body]": "Submitted."}},
    {"name": "basic_lti",      "form": {"submission[submission_type]": "basic_lti_launch","submission[url]": "https://bronston.h5p.com/lti/login"}},
    {"name": "external_tool",  "form": {"submission[submission_type]": "external_tool",   "submission[url]": "https://bronston.h5p.com/lti/login"}},
    {"name": "online_upload_empty", "form": {"submission[submission_type]": "online_upload"}},
]

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def get_item_status(page):
    r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/modules/items/{MID}")
    try:
        return await r.json()
    except Exception:
        return {"_raw_status": r.status, "_body": (await r.text())[:500]}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await login(page)

        summary = {"started": time.time(), "attempts": []}
        before = await get_item_status(page)
        (OUT / "item_before.json").write_text(json.dumps(before, indent=2))
        print("BEFORE:", json.dumps(before.get("completion_requirement"), default=str), flush=True)

        # Fetch assignment metadata to learn allowed submission_types
        r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/assignments/{AID}")
        assn = await r.json()
        (OUT / "assignment.json").write_text(json.dumps(assn, indent=2))
        print("submission_types:", assn.get("submission_types"), flush=True)

        for i, attempt in enumerate(ATTEMPTS, 1):
            print(f"\n[{i}] trying {attempt['name']}: {attempt['form']}", flush=True)
            r = await page.request.post(
                f"{BASE}/api/v1/courses/{CID}/assignments/{AID}/submissions",
                form=attempt["form"],
            )
            status = r.status
            try:
                body = await r.json()
            except Exception:
                body = {"_raw": (await r.text())[:1000]}
            (OUT / f"attempt_{i}_{attempt['name']}.json").write_text(
                json.dumps({"status": status, "body": body}, indent=2, default=str)
            )
            print(f"  -> HTTP {status}", flush=True)

            # Re-fetch module item
            after = await get_item_status(page)
            completed = (after.get("completion_requirement") or {}).get("completed")
            print(f"  -> completion_requirement.completed = {completed}", flush=True)
            summary["attempts"].append({
                "name": attempt["name"], "status": status, "completed": completed
            })
            if completed:
                print(f"SUCCESS via {attempt['name']}", flush=True)
                break

        after_final = await get_item_status(page)
        (OUT / "item_after.json").write_text(json.dumps(after_final, indent=2))
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
