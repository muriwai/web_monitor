#!/usr/bin/env python3
"""
Watches arbitrary web pages for content changes and alerts on change.

State (last-seen hash + a short text snippet) is stored under state/<name>.json
so it can be committed back to the repo by the GitHub Actions workflow between runs.

Alert channels (configure via environment variables / GitHub secrets):
  - ntfy.sh push notification: set NTFY_TOPIC (a free, unguessable topic name)
  - Email via SMTP: set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_EMAIL_TO
  - Slack/Discord webhook: set WEBHOOK_URL (posts a JSON {"text": "..."} payload)

Any subset of these may be set; each configured channel fires independently.
"""

import hashlib
import json
import os
import re
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

STATE_DIR = Path(__file__).parent / "state"
CONFIG_PATH = Path(__file__).parent / "config.yaml"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def fetch_text(url: str, selector: str | None) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    node = soup.select_one(selector) if selector else soup.body or soup
    if node is None:
        node = soup
    text = node.get_text(separator="\n", strip=True)
    return text


def clean_text(text: str, ignore_regex: list[str]) -> str:
    for pattern in ignore_regex or []:
        text = re.sub(pattern, "", text)
    # Collapse whitespace so incidental formatting shifts don't count as changes.
    return re.sub(r"\s+", " ", text).strip()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_state(name: str) -> dict | None:
    path = STATE_DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(name: str, hash_: str, snippet: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{name}.json"
    path.write_text(
        json.dumps({"hash": hash_, "snippet": snippet}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def notify(subject: str, body: str) -> None:
    ntfy_topic = os.environ.get("NTFY_TOPIC")
    if ntfy_topic:
        try:
            requests.post(
                f"https://ntfy.sh/{ntfy_topic}",
                data=body.encode("utf-8"),
                headers={"Title": subject.encode("utf-8"), "Priority": "default"},
                timeout=15,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] ntfy notify failed: {exc}", file=sys.stderr)

    webhook_url = os.environ.get("WEBHOOK_URL")
    if webhook_url:
        try:
            requests.post(webhook_url, json={"text": f"*{subject}*\n{body}"}, timeout=15)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] webhook notify failed: {exc}", file=sys.stderr)

    smtp_host = os.environ.get("SMTP_HOST")
    alert_to = os.environ.get("ALERT_EMAIL_TO")
    if smtp_host and alert_to:
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = os.environ.get("SMTP_USER", alert_to)
            msg["To"] = alert_to
            port = int(os.environ.get("SMTP_PORT", "587"))
            with smtplib.SMTP(smtp_host, port, timeout=30) as server:
                server.starttls()
                user = os.environ.get("SMTP_USER")
                password = os.environ.get("SMTP_PASS")
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] email notify failed: {exc}", file=sys.stderr)


def main() -> int:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    pages = config.get("pages", [])
    if not pages:
        print("No pages configured in config.yaml", file=sys.stderr)
        return 1

    any_error = False
    for page in pages:
        name = page["name"]
        url = page["url"]
        selector = page.get("selector") or None
        ignore_regex = page.get("ignore_regex") or []

        try:
            raw_text = fetch_text(url, selector)
        except Exception as exc:  # noqa: BLE001
            print(f"[error] fetching {name} ({url}): {exc}", file=sys.stderr)
            any_error = True
            continue

        text = clean_text(raw_text, ignore_regex)
        current_hash = hash_text(text)
        snippet = text[:300]

        previous = load_state(name)
        if previous is None:
            print(f"[init] {name}: no prior state, recording baseline")
            save_state(name, current_hash, snippet)
            continue

        if previous["hash"] != current_hash:
            print(f"[change] {name}: content changed")
            notify(
                subject=f"Page changed: {name}",
                body=f"{url}\n\nNew content starts with:\n{snippet}",
            )
            save_state(name, current_hash, snippet)
        else:
            print(f"[ok] {name}: no change")

    return 1 if any_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
