# Canvas MCV4U scraper

Walks the Bronston MCV4U course on Canvas, visits every module item in order,
captures page/assignment/quiz content, and submits quizzes with blank answers to
trip the "must submit / must view" progression gates. Resumable — rerun with the
same output root and already-completed items are skipped.

## One-time setup (inside the Codespace)

```bash
pip install --user playwright requests
python3 -m playwright install chromium
python3 -m playwright install-deps chromium
```

## Run it

```bash
export BRONSTON_USER='giscounsellor02@gmail.com'
export BRONSTON_PASS='…'
cd /workspaces/mcv4u-calculus-notes
python3 scripts/canvas_scrape/unlock_mcv4u.py 2>&1 | tee scripts/canvas_scrape/unlock.log
```

To process a single module only, set `ONLY_MODULE` to its Canvas module id
(find in `modules.json` under the `id` field):

```bash
ONLY_MODULE=3177 python3 scripts/canvas_scrape/unlock_mcv4u.py
```

## Output

- `mcv4u_scrape/unlock_state.json` — resume marker (per-item status).
- `mcv4u_scrape/course_616/unlocked_items/<item_id>_<slug>/` — one dir per item:
  - `item_meta.json` — module-item metadata
  - `final_url.txt` — URL after Canvas redirect
  - `content.{html,txt,png}` — landing page capture
  - `questions.{html,txt,png}` — quiz body (all questions on one page)
  - `main.html` — extracted main `.user_content` region for Pages

## Pulling the scrape off the Codespace

The Codespace disk is wiped on rebuild. To persist:

```bash
cd /workspaces/mcv4u-calculus-notes
tar czf mcv4u_scrape.tgz mcv4u_scrape/
# Either commit it to the repo (large), or push to a separate release artifact
```
