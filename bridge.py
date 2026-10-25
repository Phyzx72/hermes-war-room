#!/usr/bin/env python3
"""war-room bridge — the membrane between the Discord room and the disk room.

Face 1 (disk):   <room.dir>/log.jsonl — append-only, survives restarts; agents
                 read/write on their own cycles (see room.py).
Face 2 (Discord): the shared channel (config.toml [discord].channel_id) — the
                 human's live conference room.

INBOUND  (Discord -> disk): poll the channel for new messages; append each to the
  disk log tagged source="discord" (so the outbound mirror never echoes it back).
  Every message — human AND agent — is recorded: "everybody hears everything."
  @mentions are decoded to a `to` target so agents can tell who a message was for.

OUTBOUND (disk -> Discord): tail the disk log; for messages WITHOUT source="discord"
  that come FROM an agent, mirror them to the channel AS that agent (posted via
  that agent's own bot token, so it shows as the agent's own voice).

State is file-backed (restartable, no in-memory drift):
  <room.dir>/bridge.last_discord_id    last processed Discord message id
  <room.dir>/bridge.last_room_id       last mirrored disk-log message id
  <room.dir>/bridge.posted_ids.json    Discord ids the bridge itself sent (echo-skip)

Usage:
  bridge.py                 run both loops (foreground; run under systemd)
  bridge.py --inbound-once  process new Discord messages once, then exit
  bridge.py --outbound-once mirror new disk messages once, then exit
  bridge.py --dry-run       never POST to Discord; log what it would send
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from config import (
    AGENTS,
    ALL_NAMES,
    BROADCAST_WORDS,
    CHANNEL_ID,
    ID_TO_NAME,
    LAST_DISCORD,
    LAST_ROOM,
    LOG,
    OWNER_ID,
    OWNER_NAME,
    POSTED_IDS,
    TOKENS,
    UA,
    API,
)


def _reader_token() -> str | None:
    """Any bot token that can read the channel (all bots in the room can)."""
    for tok in TOKENS.values():
        if tok:
            return tok
    return None


def _api(method, path, token, payload=None, timeout=15):
    url = API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bot {token}", "User-Agent": UA,
                 "Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _plain_name_target(text: str) -> str | None:
    """Detect a leading plain-name or @name address ('alice are you there?')."""
    t = text.strip()
    low = t.lower()
    for name in sorted(ALL_NAMES, key=len, reverse=True):
        if low.startswith("@" + name) and (
            len(low) == len(name) + 1 or not low[len(name) + 1].isalnum()
        ):
            return name
    for name in sorted(ALL_NAMES, key=len, reverse=True):
        if low.startswith(name) and (
            len(low) == len(name) or low[len(name)] in " ,:!?.@-"
        ):
            return name
    return None


def fetch_messages_after(last_id: str) -> list:
    """Newest-first list of channel messages with id > last_id (ascending)."""
    tok = _reader_token()
    if not tok:
        return []
    path = f"/channels/{CHANNEL_ID}/messages?limit=50"
    if last_id:
        path += f"&after={last_id}"
    resp = _api("GET", path, tok)
    msgs = json.load(resp)
    msgs.sort(key=lambda m: int(m["id"]))
    return msgs


def decode_mentions(content: str, mentions: list) -> tuple[str, str]:
    """Return (to, cleaned_content). `to` is an agent name or '*' (broadcast)."""
    mentioned = []
    for m in mentions or []:
        name = ID_TO_NAME.get(m.get("id"))
        if name:
            mentioned.append(name)
        elif m.get("id") == OWNER_ID:
            mentioned.append(OWNER_NAME.lower())

    cleaned = content
    for m in mentions or []:
        nm = ID_TO_NAME.get(m.get("id"), OWNER_NAME.lower() if m.get("id") == OWNER_ID else None)
        cleaned = cleaned.replace(f"<@{m.get('id')}>", f"@{nm}" if nm else "@user")
        cleaned = cleaned.replace(f"<@!{m.get('id')}>", f"@{nm}" if nm else "@user")

    low = content.lower()
    if any(
        ("@" + w) in low or low.strip() == w or low.startswith(w + " ")
        for w in BROADCAST_WORDS
    ):
        return "*", cleaned

    if mentioned:
        return mentioned[0], cleaned

    plain = _plain_name_target(content)
    if plain:
        return plain, cleaned

    return "*", cleaned


def read_last(path: Path) -> str:
    return path.read_text().strip() if path.exists() else ""


def write_last(path: Path, val: str) -> None:
    path.write_text(val)


def load_posted_ids() -> list:
    if POSTED_IDS.exists():
        try:
            return json.loads(POSTED_IDS.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_posted_ids(ids: list) -> None:
    POSTED_IDS.write_text(json.dumps(ids[-200:]))


def append_discord_to_log(msg: dict) -> None:
    """Record one Discord message into the disk log (source=discord)."""
    author = msg.get("author", {})
    author_id = author.get("id")
    author_name = author.get("username", "unknown")
    is_bot = bool(author.get("bot"))

    if author_id == OWNER_ID:
        sender = OWNER_NAME.lower()
    elif is_bot:
        sender = ID_TO_NAME.get(author_id, author_name.lower())
    else:
        sender = author_name.lower()

    content = msg.get("content", "") or ""
    if not content.strip():
        return  # skip embed-only / attachment-only messages

    to, cleaned = decode_mentions(content, msg.get("mentions", []))

    record = {
        "id": f"discord-{msg['id']}",
        "from": sender,
        "to": to,
        "thread": None,
        "kind": "note",
        "body": cleaned.strip(),
        "refs": [],
        "ts": msg.get("timestamp", "").replace("T", " ")[:19],
        "source": "discord",
    }
    with open(LOG, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def inbound_once(dry: bool = False) -> int:
    last = read_last(LAST_DISCORD)
    posted = set(load_posted_ids())
    msgs = fetch_messages_after(last)
    newest = last
    recorded = 0
    for m in msgs:
        mid = m["id"]
        if mid in posted:  # our own mirror — never re-ingest
            newest = max(newest, mid)
            continue
        append_discord_to_log(m)
        newest = max(newest, mid)
        recorded += 1
    if newest != last:
        write_last(LAST_DISCORD, newest)
    return recorded


def mirror_to_discord(record: dict, dry: bool) -> bool:
    """Post one disk-room agent message to the channel as that agent's bot."""
    agent = record.get("from", "")
    tok = TOKENS.get(agent)
    if agent not in AGENTS or not tok:
        return False

    body = (record.get("body") or "").strip()
    if not body:
        return False

    kind = record.get("kind", "note")
    to = record.get("to", "*")

    if kind == "raise":
        content = f"🖐️ {body}"
    elif to not in ("*", OWNER_NAME.lower()):
        content = f"`→ {to}` {body}"
    else:
        content = body

    if len(content) > 1990:
        content = content[:1990] + "…"

    if dry:
        print(f"[dry-run] would post as {agent}: {content[:120]}")
        return True

    try:
        resp = _api("POST", f"/channels/{CHANNEL_ID}/messages",
                    tok, payload={"content": content})
        sent = json.load(resp)
        posted = load_posted_ids()
        posted.append(sent["id"])
        save_posted_ids(posted)
        return True
    except urllib.error.HTTPError as e:
        print(f"[mirror] {agent} POST -> HTTP {e.code}: {e.read().decode()[:200]}",
              file=sys.stderr)
        return False
    except Exception as e:
        print(f"[mirror] {agent} error: {e}", file=sys.stderr)
        return False


def read_log_records() -> list:
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


def outbound_once(dry: bool = False) -> int:
    last = read_last(LAST_ROOM)
    posted = 0
    newest = last
    for rec in read_log_records():
        rid = rec.get("id", "")
        if rec.get("source") == "discord":
            if rid > newest:
                newest = rid
            continue
        if rec.get("from") not in AGENTS:
            if rid > newest:
                newest = rid
            continue
        if rid <= last:
            continue
        if mirror_to_discord(rec, dry):
            posted += 1
        if rid > newest:
            newest = rid
    if newest != last:
        write_last(LAST_ROOM, newest)
    return posted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inbound-once", action="store_true")
    ap.add_argument("--outbound-once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--discord-interval", type=float, default=2.0)
    ap.add_argument("--room-interval", type=float, default=1.0)
    args = ap.parse_args()

    if args.inbound_once:
        n = inbound_once(args.dry_run)
        print(f"inbound: recorded {n} message(s)")
        return
    if args.outbound_once:
        n = outbound_once(args.dry_run)
        print(f"outbound: mirrored {n} message(s)")
        return

    print("war-room bridge: running inbound + outbound loops", flush=True)
    while True:
        try:
            inbound_once(args.dry_run)
        except Exception as e:
            print(f"inbound error: {e}", file=sys.stderr)
        try:
            outbound_once(args.dry_run)
        except Exception as e:
            print(f"outbound error: {e}", file=sys.stderr)
        time.sleep(min(args.discord_interval, args.room_interval))


if __name__ == "__main__":
    main()
