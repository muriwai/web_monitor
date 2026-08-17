# Page Watcher

Watches arbitrary web pages for content changes and alerts you when they change.
Runs for free on GitHub Actions — no server to host or pay for.

## How it works

- `config.yaml` lists the URLs you want watched (add as many as you like).
- On a schedule (every 30 min by default), GitHub Actions runs `monitor.py`, which
  fetches each page, extracts and normalizes its text, and hashes it.
- The hash is compared against the last-seen hash stored in `state/<name>.json`
  (committed back to the repo by the workflow itself — that's the "free database").
- If the hash differs, it fires whichever alert channels you've configured.

## Setup (5 minutes)

1. Create a new GitHub repo (private is fine) and push this folder to it:

   ```bash
   git init
   git add .
   git commit -m "Initial page watcher"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```

2. Choose at least one alert channel and add it as a repo secret
   (Settings → Secrets and variables → Actions → New repository secret):

   **Push notification (easiest, no account needed):**
   - Install the [ntfy app](https://ntfy.sh/) (iOS/Android) or just use a browser at `ntfy.sh/<your-topic>`.
   - Pick a hard-to-guess topic name (it's public by topic name, so don't use something guessable).
   - Add secret `NTFY_TOPIC` = `your-chosen-topic-name`.
   - Subscribe to that topic in the app.

   **Email:**
   - Add secrets `SMTP_HOST`, `SMTP_PORT` (usually 587), `SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL_TO`.
   - For Gmail: use an [App Password](https://myaccount.google.com/apppasswords), host `smtp.gmail.com`, port `587`.

   **Slack/Discord webhook:**
   - Create an incoming webhook URL from Slack or Discord.
   - Add secret `WEBHOOK_URL`.

3. Edit `config.yaml` to add/remove pages. Each entry needs:
   - `name` — short unique label (used as the state filename and in alerts)
   - `url` — the page to watch
   - `selector` (optional) — CSS selector to narrow the comparison (avoids false
     alerts from ads, "last viewed" timestamps, etc. elsewhere on the page)
   - `ignore_regex` (optional) — regex patterns to strip before comparing

4. Push your changes. The workflow runs automatically on schedule, and you can
   trigger it manually from the repo's **Actions** tab → "Watch pages for changes"
   → **Run workflow**, to test it immediately.

## Adjusting frequency

Edit the `cron` line in `.github/workflows/monitor.yml`. GitHub's minimum
granularity is 5 minutes, but scheduled workflows are best-effort and can lag
during high load — every 15–30 min is a realistic floor for reliability.

## Local testing

```bash
pip install -r requirements.txt
NTFY_TOPIC=your-topic python monitor.py
```

First run just records a baseline (no alert). Change the page (or edit
`state/<name>.json` by hand to force a mismatch) and run again to see an alert fire.
