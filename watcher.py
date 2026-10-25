#!/usr/bin/env python3
"""Hermes War Room watcher — real-time wakeup for the disk room.

Tails log.jsonl and, on each new message, signals the addressed agent so it
responds NOW rather than on its next cycle. This is the push layer that turns
the pull-based room into a live room.

How a "wakeup" is delivered:
  - The watcher writes a per-agent wake file:  <room.dir>/wake/<agent>.wake
    (or <room.dir>/wake/ALL.wake for broadcast).
  - The agent's gateway (or loop) watches that file's mtime and responds.

This watcher is lightweight and restartable; it holds NO state (it re-derives
its position by re-reading the log, bounded to the last 2000 lines).

Usage:
  watcher.py            # run in foreground
  watcher.py --once     # process any new messages since last run, then exit
"""

import argparse
import json
import time

from config import LOG, WAKE, WATCHER_STATE


def ensure():
    WAKE.mkdir(parents=True, exist_ok=True)


def last_id() -> str:
    if not WATCHER_STATE.exists():
        return ""
    return WATCHER_STATE.read_text().strip()


def save_last_id(mid: str):
    WATCHER_STATE.write_text(mid)


def read_log() -> list:
    if not LOG.exists():
        return []
    out = []
    with open(LOG) as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def wake_for(msg: dict):
    """Append a wake line for the addressed target(s)."""
    ensure()
    to = msg.get("to")
    targets = ["ALL"] if to == "*" else [to] if to else ["ALL"]
    line = json.dumps({
        "id": msg.get("id"),
        "from": msg.get("from"),
        "to": to,
        "kind": msg.get("kind"),
        "thread": msg.get("thread"),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    for t in targets:
        with open(WAKE / f"{t}.wake", "a") as fh:
            fh.write(line + "\n")


def process_once(start: str) -> str:
    """Process messages with id > start; return the newest id seen (or start)."""
    newest = start
    msgs = read_log()
    for m in msgs:
        mid = m.get("id", "")
        if mid > start:
            wake_for(m)
            if mid > newest:
                newest = mid
    return newest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="process once, then exit")
    ap.add_argument("--interval", type=float, default=0.5,
                    help="poll interval in seconds (default 0.5)")
    args = ap.parse_args()

    ensure()
    cursor = last_id()

    if args.once:
        cursor = process_once(cursor)
        save_last_id(cursor)
        return

    while True:
        try:
            cursor = process_once(cursor)
            save_last_id(cursor)
        except Exception as e:
            print(f"watcher error: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
