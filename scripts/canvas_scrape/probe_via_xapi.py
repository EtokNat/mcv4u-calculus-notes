"""Attempt to unlock Lesson 1.1 Interactive Video Check via xAPI completed statement.

Flow:
  1. Login to Canvas as the shared staff account.
  2. Load the assignment page so the H5P LTI session cookies are established on bronston.h5p.com.
  3. Read H5PIntegration from the H5P frame to confirm endpoint + content_id.
  4. POST an xAPI "completed" statement to https://bronston.h5p.com/lti/content/<cid>/statements
  5. Also try POST to /attempts endpoint with a scored attempt.
  6. Re-check /api/v1/courses/616/assignments/17404/submissions/self — did workflow_state flip?

All request/response dumps go to ./xapi_unlock/.
"""
import os, json, pathlib, asyncio, time, uuid
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

USER = os.environ["BRONSTON_USER"]
PASS = os.environ["BRONSTON_PASS"]
BASE = "https://bronston.instructure.com"
CID  = "616"
AID  = 17404
H5P_CONTENT_ID = "1293044797216683108"
OUT  = pathlib.Path(os.environ.get("OUT_ROOT", "./xapi_unlock")).resolve()
OUT.mkdir(parents=True, exist_ok=True)

async def login(page):
    await page.goto(f"{BASE}/login/canvas", wait_until="domcontentloaded")
    await page.fill('#pseudonym_session_unique_id', USER)
    await page.fill('#pseudonym_session_password', PASS)
    await page.locator('#login_form input[type="submit"][name="commit"]').click()
    await page.wait_for_url("**/?login_success=1", timeout=20000)

async def submission_state(page, tag):
    r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/assignments/{AID}/submissions/self")
    status = r.status
    try:
        body = await r.json()
    except Exception:
        body = {"_raw": (await r.text())[:500]}
    (OUT / f"submission_{tag}.json").write_text(json.dumps({"status": status, "body": body}, indent=2, default=str))
    ws = body.get("workflow_state") if isinstance(body, dict) else "?"
    sub_at = body.get("submitted_at") if isinstance(body, dict) else "?"
    print(f"  submission[{tag}]: HTTP {status} workflow_state={ws} submitted_at={sub_at}", flush=True)
    return body

async def h5p_integration_from_frame(page):
    """Visit the assignment page, wait for H5P iframe to boot, dump H5PIntegration."""
    await page.goto(f"{BASE}/courses/{CID}/assignments/{AID}",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(10000)
    for f in page.frames:
        if "h5p.com" in (f.url or ""):
            try:
                d = await f.evaluate("() => (typeof H5PIntegration !== 'undefined') ? JSON.parse(JSON.stringify(H5PIntegration)) : null")
                if d:
                    return f, d
            except Exception:
                continue
    return None, None

async def post_statement(ctx, endpoint, payload, tag, frame=None):
    """POST xAPI statement. If a frame is given, run the fetch INSIDE the frame so
    partitioned third-party cookies travel with the request (CHIPS-compatible).
    Also pulls authenticity_token from the frame's bootstrap data as X-CSRF-Token."""
    if frame is not None:
        try:
            result = await frame.evaluate(
                """async ({endpoint, payload}) => {
                    try {
                        // Hunt for authenticity_token in several locations
                        let csrf = null;
                        const meta = document.querySelector('meta[name="csrf-token"]');
                        if (meta) csrf = meta.content;
                        if (!csrf) {
                            // Try to pull from inline <script> JSON blobs
                            for (const s of document.querySelectorAll('script')) {
                                const m = (s.textContent||'').match(/"authenticity_token"\\s*:\\s*"([^"]+)"/);
                                if (m) { csrf = m[1]; break; }
                            }
                        }
                        const headers = {'Content-Type': 'application/json'};
                        if (csrf) {
                            headers['X-CSRF-Token'] = csrf;
                            headers['X-Requested-With'] = 'XMLHttpRequest';
                        }
                        const r = await fetch(endpoint, {
                            method: 'POST',
                            headers,
                            credentials: 'include',
                            body: JSON.stringify(payload),
                        });
                        const text = await r.text();
                        let json = null;
                        try { json = JSON.parse(text); } catch(_) {}
                        return {status: r.status, csrf_used: !!csrf, text: text.slice(0, 2000), json};
                    } catch (e) { return {error: String(e)}; }
                }""",
                {"endpoint": endpoint, "payload": payload},
            )
        except Exception as e:
            result = {"error": str(e)}
        (OUT / f"{tag}.json").write_text(json.dumps({
            "endpoint": endpoint,
            "payload": payload,
            "result": result,
            "via": "frame.evaluate(fetch)",
        }, indent=2, default=str))
        print(f"  POST {tag} (in-frame): {result.get('status') or result.get('error')}", flush=True)
        return result.get("status"), result
    else:
        r = await ctx.request.post(
            endpoint,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
        )
        try:
            body = await r.json()
        except Exception:
            body = {"_raw": (await r.text())[:1000]}
        (OUT / f"{tag}.json").write_text(json.dumps({
            "endpoint": endpoint,
            "payload": payload,
            "status": r.status,
            "response": body,
        }, indent=2, default=str))
        print(f"  POST {tag}: HTTP {r.status}", flush=True)
        return r.status, body

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 2200})
        page = await ctx.new_page()
        print("Logging in...", flush=True)
        await login(page)

        await submission_state(page, "before")

        print("Loading assignment to establish H5P session...", flush=True)
        frame, h5p_int = await h5p_integration_from_frame(page)
        if not h5p_int:
            print("ERROR: H5PIntegration not found in any frame", flush=True)
            await browser.close()
            return
        (OUT / "h5p_integration.json").write_text(json.dumps(h5p_int, indent=2, default=str))
        print(f"  H5P ajax endpoints: {h5p_int.get('ajax')}", flush=True)

        # Dump cookies for inspection
        cookies = await ctx.cookies()
        (OUT / "cookies.json").write_text(json.dumps(cookies, indent=2, default=str))
        h5p_cookies = [c for c in cookies if "h5p.com" in c.get("domain","")]
        print(f"  cookies on h5p.com: {len(h5p_cookies)}", flush=True)

        # Build the real endpoint URLs
        xapi_url   = h5p_int["ajax"]["xapi"].replace(":contentId", H5P_CONTENT_ID)
        result_url = h5p_int["ajax"]["xAPIResult"].replace(":contentId", H5P_CONTENT_ID)
        print(f"  xapi:   {xapi_url}", flush=True)
        print(f"  result: {result_url}", flush=True)

        content_entry = h5p_int.get("contents", {}).get(f"cid-{H5P_CONTENT_ID}", {})
        activity_url = content_entry.get("url") or f"https://bronston.h5p.com/content/{H5P_CONTENT_ID}"

        # Statement A: minimal completed
        stmt_completed = {
            "actor": {"objectType": "Agent", "account": {"name": "scraper", "homePage": "https://bronston.instructure.com"}},
            "verb": {"id": "http://adlnet.gov/expapi/verbs/completed",
                     "display": {"en-US": "completed"}},
            "object": {
                "id": activity_url,
                "objectType": "Activity",
                "definition": {
                    "name": {"en-US": content_entry.get("title","Interactive Video")},
                    "type": "http://adlnet.gov/expapi/activities/interaction",
                }
            },
            "result": {
                "completion": True,
                "success": True,
                "duration": "PT2M33S",
                "score": {"min": 0, "max": 1, "raw": 1, "scaled": 1.0},
            },
            "context": {"contextActivities": {"category": [{"id": "http://h5p.org/libraries/H5P.InteractiveVideo-1.28"}]}},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        await post_statement(ctx, xapi_url, stmt_completed, "attempt1_completed", frame=frame)

        await submission_state(page, "after_completed")

        # Statement B: answered (sometimes required to count as a submission)
        stmt_answered = dict(stmt_completed)
        stmt_answered["verb"] = {"id": "http://adlnet.gov/expapi/verbs/answered",
                                 "display": {"en-US": "answered"}}
        await post_statement(ctx, xapi_url, stmt_answered, "attempt2_answered", frame=frame)
        await submission_state(page, "after_answered")

        # Statement C: via /attempts endpoint
        attempt_payload = {
            "completion": True,
            "success": True,
            "score": {"raw": 1, "max": 1, "scaled": 1.0, "min": 0},
            "duration": "PT2M33S",
            "statement": stmt_completed,
        }
        await post_statement(ctx, result_url, attempt_payload, "attempt3_attempts_endpoint", frame=frame)
        await submission_state(page, "after_attempts")

        # Re-visit the module item URL to see if the completion propagated
        try:
            r = await page.request.get(f"{BASE}/api/v1/courses/{CID}/modules/3177/items?include[]=content_details")
            items = await r.json()
            (OUT / "module_items_after.json").write_text(json.dumps(items, indent=2, default=str))
            for it in items:
                if it.get("id") in (41134, 32371, 32383):
                    cr = it.get("completion_requirement") or {}
                    print(f"  module_item {it['id']} ({it.get('title')!r}): completed={cr.get('completed')}", flush=True)
        except Exception as e:
            (OUT / "module_items_err.txt").write_text(str(e))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
