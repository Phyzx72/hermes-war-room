#!/usr/bin/env python3
"""Hermes War Room — a disk-backed, append-only message bus between your agents.

Borrows the A2A/Handoff *contract* (agent cards, from/to/thread addressing,
decentralized routing) from Microsoft Agent Framework. Implements it on the
shared filesystem. No runtime, no server, no orchestrator.

RULES ENFORCED (anti-crosstalk discipline):
  R1: every message names a `to` (a specific agent, or "*" to broadcast).
  R2: only the addressee(s) reply; a question is answered once per thread.
  R3: a `thread` binds a conversation; replies carry the same thread.
  R4: nobody writes another agent's card. A `handoff` is a suggestion, not a command.

AMBIENT-ROOM ETIQUETTE:
  - Everybody hears everything (a `to="*"` broadcast reaches all; a named `to`
    still lands in the shared log so all can read it).
  - The named agent owns the answer.
  - Any OTHER agent may raise a hand with `kind="raise"` — brief, self-flagged,
    stating why it's coming from them.

This module is BOTH a CLI (`room.py post|read|seen|mark-seen|thread|cards`)
and a library (`import room; room.append(...); room.read_for(...)`).
The library functions are canonical; the CLI functions are thin wrappers.

Layout (ROOM_DIR, from config.toml [room].dir):
  log.jsonl      append-only; single source of truth
  cards/<agent>.json
  seen/<agent>.txt   last-read cursor
  wake/<agent>.wake  watcher wakeup signals
  LOCK           flock target
"""

import argparse
import fcntl
import json
import sys
import time

from config import CARDS, LOG, LOCK, ROOM_DIR, SEEN

KINDS = {"question", "answer", "handoff", "note", "ack", "raise"}


# ------------------------------ core primitives ------------------------------

def ensure_layout():
    for d in (CARDS, SEEN):
        d.mkdir(parents=True, exist_ok=True)
    if not LOG.exists():
        LOG.touch()


def _gen_id() -> str:
    return "room-{}-{}".format(int(time.time() * 1000), __import__("os").getpid() % 1000)


def _lock():
    f = open(LOCK, "a")
    fcntl.flock(f, fcntl.LOCK_EX)
    return f


def _unlock(f):
    fcntl.flock(f, fcntl.LOCK_UN)
    f.close()


# ------------------------------ library API ---------------------------------

def append(sender: str, to: str, kind: str, body: str,
           thread: str = None, refs: list = None) -> dict:
    """Append one message atomically; return the message."""
    ensure_layout()
    if kind not in KINDS:
        kind = "note"
    if not to:
        raise ValueError("R1: every message must name a `to` ('*' = broadcast)")
    msg = {
        "id": _gen_id(),
        "from": sender,
        "to": to,
        "thread": thread,
        "kind": kind,
        "body": body,
        "refs": refs or [],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    f = _lock()
    try:
        with open(LOG, "a") as fh:
            fh.write(json.dumps(msg) + "\n")
    finally:
        _unlock(f)
    return msg


def read_all() -> list:
    """Every message in the log, in order."""
    ensure_layout()
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


def last_seen(agent: str) -> str:
    p = SEEN / "{}.txt".format(agent)
    return p.read_text().strip() if p.exists() else ""


def is_addressed(msg: dict, agent: str) -> bool:
    to = msg.get("to")
    return to == "*" or to == agent


def read_for(agent: str, unread_only: bool = True) -> list:
    """Messages addressed to `agent`. If unread_only, only those after cursor."""
    ensure_layout()
    last = last_seen(agent) if unread_only else ""
    return [m for m in read_all()
            if is_addressed(m, agent) and (not unread_only or m.get("id", "") > last)]


def mark_seen(agent: str) -> str:
    """Advance cursor to newest message id; return that id (or '')."""
    ensure_layout()
    msgs = read_all()
    if not msgs:
        return ""
    latest = max(m.get("id", "") for m in msgs)
    (SEEN / "{}.txt".format(agent)).write_text(latest)
    return latest


def thread_messages(thread_id: str) -> list:
    return [m for m in read_all() if m.get("thread") == thread_id]


def list_cards() -> list:
    out = []
    for p in sorted(CARDS.glob("*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            out.append({"name": p.name, "error": "invalid json"})
    return out


# ------------------------------ CLI wrappers ---------------------------------

def _cli_post(args):
    try:
        m = append(args.from_, args.to, args.kind, args.body, thread=args.thread)
    except ValueError as e:
        sys.exit(str(e))
    print(json.dumps(m))


def _cli_read(args):
    msgs = read_all() if args.all else read_for(args.__dict__.get("for"))
    for m in msgs:
        print(json.dumps(m))


def _cli_seen(args):
    print(last_seen(args.__dict__.get("for")))


def _cli_mark_seen(args):
    print(mark_seen(args.__dict__.get("for")))


def _cli_thread(args):
    msgs = thread_messages(args.id)
    if not msgs:
        sys.exit("no thread '{}'".format(args.id))
    for m in msgs:
        print("{} {}{} [{}] {}".format(
            m.get("ts"), m.get("from"),
            " -> {}".format(m.get("to")) if m.get("to") != "*" else " -> *",
            m.get("kind"), m.get("body")[:200]))


def _cli_cards(args):
    for c in list_cards():
        print("{}: {} | hands to: {}".format(
            c.get("name"), c.get("role", ""), ", ".join(c.get("handoff", []))))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("post")
    p.add_argument("--from", dest="from_", required=True)
    p.add_argument("--to", required=True)
    p.add_argument("--kind", default="note")
    p.add_argument("--thread", default=None)
    p.add_argument("--body", required=True)
    p.set_defaults(func=_cli_post)

    p = sub.add_parser("read")
    p.add_argument("--for", dest="for", required=True)
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=_cli_read)

    p = sub.add_parser("seen")
    p.add_argument("--for", dest="for", required=True)
    p.set_defaults(func=_cli_seen)

    p = sub.add_parser("mark-seen")
    p.add_argument("--for", dest="for", required=True)
    p.set_defaults(func=_cli_mark_seen)

    p = sub.add_parser("thread")
    p.add_argument("--id", dest="id", required=True)
    p.set_defaults(func=_cli_thread)

    p = sub.add_parser("cards")
    p.set_defaults(func=_cli_cards)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
