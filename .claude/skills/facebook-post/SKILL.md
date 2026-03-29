# Facebook Post — External Action Skill

## Description

Posts a text status update to a Facebook profile or page via Playwright browser
automation. Requires explicit human approval (HITL checkbox gate) before any post
is published. Maintains a persistent browser session in `.fb_session/` to avoid
repeated logins.

**Script:** `scripts/post_facebook.py`

## Trigger

Run this skill when a task requires posting to Facebook AND the human has ticked
`- [x] **Approve Action:**` in the corresponding Plan file.

```bash
python scripts/post_facebook.py --task-id TASK_20260301T120000.md
```

## Inputs

| Input           | Source                                              | Required |
|-----------------|-----------------------------------------------------|----------|
| `post_content`  | `## Full Content` section in the task file body     | Yes      |

## Procedure

1. Load persistent Chromium session from `.fb_session/`
2. Navigate to `facebook.com` — login if session expired
3. Click "What's on your mind" to open the compose modal
4. `editor.focus()` + `keyboard.type(content, delay=80)` — fires real input events
5. Click "Post" button once it becomes enabled
6. Verify modal closed (success) — take screenshot as proof
7. Log result to `Logs/YYYY-MM-DD.json`
8. Update `Dashboard.md` Recent Activity

## Constraints

- **Never post without approval** — HITL checkbox must be ticked
- **Rate limit:** max 10 posts/day
- **Char limit:** 63,206 characters (Facebook limit)
- **DRY_RUN=true** → logs intent, does not post
- **Credentials:** `FACEBOOK_EMAIL` + `FACEBOOK_PASSWORD` in `.env`
- **Session:** `FACEBOOK_SESSION_DIR` (default: `.fb_session/`)
- **Headless:** `FACEBOOK_HEADLESS=false` (default, visible window)
