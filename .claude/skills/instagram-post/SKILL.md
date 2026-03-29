# Instagram Post — External Action Skill

## Description

Posts a photo with caption to an Instagram account via Playwright browser automation.
Instagram feed posts **require an image** — the image path must be specified in the
task file's frontmatter as `image_path`. Maintains a persistent browser session in
`.ig_session/` to avoid repeated logins.

**Script:** `scripts/post_instagram.py`

## Trigger

Run this skill when a task requires posting to Instagram AND the human has ticked
`- [x] **Approve Action:**` in the corresponding Plan file.

```bash
python scripts/post_instagram.py --task-id TASK_20260301T120000.md
```

## Inputs

| Input          | Source                                              | Required |
|----------------|-----------------------------------------------------|----------|
| `image_path`   | `image_path:` field in YAML frontmatter             | Yes      |
| `caption`      | `## Full Content` section in the task file body     | Yes      |

## Task File Example

```markdown
---
type: task
skill: instagram-post
image_path: /mnt/c/h-0/Ai_employee_vault_bronze/assets/post_image.jpg
---

## Full Content

Building our AI Employee pipeline — fully automated, local-first, human-in-the-loop.
Check the link in bio for the full walkthrough.

#AI #Automation #BuildInPublic
```

## Procedure

1. Load persistent Chromium session from `.ig_session/`
2. Navigate to `instagram.com` — login if session expired
3. Click "+" (Create) button in navigation bar
4. Handle file chooser → upload image from `image_path`
5. Navigate through the wizard: Select → Crop → Filters → Caption
6. `keyboard.type(caption, delay=80)` in the caption field
7. Click "Share" to publish
8. Take screenshot as proof of success
9. Log result to `Logs/YYYY-MM-DD.json`
10. Update `Dashboard.md` Recent Activity

## Constraints

- **Never post without approval** — HITL checkbox must be ticked
- **Image required:** Instagram feed posts require a local image file
- **Rate limit:** max 10 posts/day
- **Caption limit:** 2,200 characters (Instagram limit)
- **DRY_RUN=true** → logs intent, does not post
- **Credentials:** `INSTAGRAM_USERNAME` + `INSTAGRAM_PASSWORD` in `.env`
- **Session:** `INSTAGRAM_SESSION_DIR` (default: `.ig_session/`)
- **Headless:** `INSTAGRAM_HEADLESS=false` (default, visible window)
