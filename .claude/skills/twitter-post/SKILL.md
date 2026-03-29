# Twitter/X Post — External Action Skill

## Description

Posts a tweet to Twitter/X via Playwright browser automation. Maintains a persistent
browser session in `.x_session/` to avoid repeated logins. Enforces Twitter's 280
character limit before posting.

**Script:** `scripts/post_twitter.py`

## Trigger

Run this skill when a task requires posting to Twitter/X AND the human has ticked
`- [x] **Approve Action:**` in the corresponding Plan file.

```bash
python scripts/post_twitter.py --task-id TASK_20260301T120000.md
```

## Inputs

| Input          | Source                                              | Required |
|----------------|-----------------------------------------------------|----------|
| `tweet_content`| `## Full Content` section in the task file body     | Yes      |

## Procedure

1. Load persistent Chromium session from `.x_session/`
2. Navigate to `x.com` — login if session expired
3. Click the compose text area (always visible on X feed)
4. `editor.focus()` + `keyboard.type(content, delay=80)` — fires real input events
5. Click "Post" button once it becomes enabled
6. Verify the tweet appeared / modal closed — take screenshot as proof
7. Log result to `Logs/YYYY-MM-DD.json`
8. Update `Dashboard.md` Recent Activity

## Constraints

- **Never post without approval** — HITL checkbox must be ticked
- **Rate limit:** max 10 posts/day
- **Char limit:** 280 characters (Twitter/X hard limit — content is truncated with warning)
- **DRY_RUN=true** → logs intent, does not post
- **Credentials:** `TWITTER_EMAIL` + `TWITTER_PASSWORD` in `.env`
- **Session:** `TWITTER_SESSION_DIR` (default: `.x_session/`)
- **Headless:** `TWITTER_HEADLESS=false` (default, visible window)
