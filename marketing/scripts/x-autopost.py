#!/usr/bin/env python3
"""
FQ — free X (Twitter) auto-poster.

Posts ONE tweet per run from content/tweets.csv, rotating deterministically by
time slot so it cycles through the whole bank before repeating (evergreen) — no
state file, no commit-back needed. Uses the X API **Free** tier (write), so the
running cost is $0.

Run it from any cron: GitHub Actions, Railway, a VPS, or your laptop. See
docs/X_AUTOPOST_SETUP.md.

Env (set as secrets, never commit them):
  X_API_KEY, X_API_SECRET            -> app consumer key/secret
  X_ACCESS_TOKEN, X_ACCESS_SECRET    -> your account's access token/secret
Optional:
  POST_INTERVAL_HOURS  (default 8)   -> must match your cron spacing
  AUTOPOST_DRYRUN=1                  -> print what would post, don't post
  AUTOPOST_INDEX=N                   -> force a specific row (testing)
  TWEET_MAX_LEN  (default 280)

Posting cap: Free tier allows ~1,500 posts/month — far above 1-3/day.
Compliance: the bank is pre-vetted (no profit promises). Keep it that way.
"""
import csv
import os
import sys
import time
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "content" / "tweets.csv"


def load_tweets():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("text", "").strip()]
    if not rows:
        sys.exit("No tweets in content/tweets.csv")
    return rows


def pick_index(n):
    if os.getenv("AUTOPOST_INDEX"):
        return int(os.getenv("AUTOPOST_INDEX")) % n
    interval = float(os.getenv("POST_INTERVAL_HOURS", "8")) * 3600
    # Monotonic time-slot → advances by 1 each scheduled run, wraps after n (evergreen).
    return int(time.time() // interval) % n


def main():
    rows = load_tweets()
    row = rows[pick_index(len(rows))]
    text = row["text"].strip()
    max_len = int(os.getenv("TWEET_MAX_LEN", "280"))

    if len(text) > max_len:
        print(f"WARN: tweet #{row.get('id')} is {len(text)} chars (> {max_len}).")

    creds = {
        "consumer_key": os.getenv("X_API_KEY"),
        "consumer_secret": os.getenv("X_API_SECRET"),
        "access_token": os.getenv("X_ACCESS_TOKEN"),
        "access_token_secret": os.getenv("X_ACCESS_SECRET"),
    }
    dry = os.getenv("AUTOPOST_DRYRUN") == "1" or not all(creds.values())

    if dry:
        why = "DRYRUN" if os.getenv("AUTOPOST_DRYRUN") == "1" else "missing API keys"
        print(f"[{why}] would post tweet #{row.get('id')} ({row.get('pillar')}, "
              f"{len(text)} chars):\n{text}")
        return  # exit 0 — so cron without secrets doesn't spam failures

    import tweepy  # imported here so dry-runs need no dependency
    client = tweepy.Client(**creds)
    resp = client.create_tweet(text=text)
    tid = resp.data.get("id") if resp and resp.data else "?"
    print(f"posted tweet #{row.get('id')} -> https://x.com/i/status/{tid}")


if __name__ == "__main__":
    main()
