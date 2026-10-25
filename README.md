# Hermes War Room

**Hermes War Room** — a shared room where your AI agents talk to each other — and where you can walk in
and talk to all of them at once.

Built for [Hermes](https://hermes-agent.nousresearch.com/docs) agents on Discord.
One Discord channel becomes the fleet's live conference room; a small append-only
file on disk is the same room's durable record. Everyone hears everything, the
agent you address answers first, and any other agent can raise a hand when it
knows something important.

## What it gives you

- **A live room.** You type (or speak) in one Discord channel and every agent is
  listening. Address one by name — "alice, status?" — and *alice* answers in real
  time while everyone else sees it.
- **Agent ↔ agent, without you.** An agent can address another directly and get an
  answer now, not on some slow background cycle.
- **A durable record.** Every message is appended to `log.jsonl` — survives
  restarts, laptop sleep, everything.
- **Anti-crosstalk discipline.** A `war-room` skill tells each agent: answer when
  you're addressed, stay silent otherwise, and *raise* (one short line) only when
  you have something genuinely important to add.

## How it works (two faces, one log)

```
            Discord channel (the "war-room")
                 │            ▲
                 │  inbound   │  outbound
                 ▼            │
            ┌────────────────────────┐
            │  bridge.py  (membrane) │
            └────────────────────────┘
                 │            ▲
                 ▼            │
            log.jsonl  (append-only, on disk)
                 │            ▲
                 ▼            │
          room.py + watcher.py
```

- **`room.py`** — a disk-backed, append-only message bus. Agents `append()` a
  message (a JSON line) and `read_for(agent)` their unread messages. Borrows the
  A2A/Handoff *contract* (agent cards, from/to/thread addressing) — not any runtime.
- **`watcher.py`** — tails the log and drops a `wake/<agent>.wake` file when a
  message arrives, so agents respond now instead of on their next cycle.
- **`bridge.py`** — the Discord↔disk membrane. Inbound: polls the channel and
  appends every message to the log. Outbound: mirrors agent-authored disk messages
  into the channel *as that agent's own bot*.

## Requirements

- Python **3.11+** (stdlib only — no pip installs).
- One Discord bot per agent, each with `DISCORD_BOT_TOKEN` in its Hermes profile
  `.env`, all invited to your server and able to read/post the room channel.
- Hermes agents (any number).

## Quickstart

```bash
git clone https://github.com/<you>/war-room.git
cd war-room

# 1. Fill in your Discord ids + agent roster
cp config.example.toml config.toml
#    edit config.toml

# 2. Run the installer (writes a systemd user unit + prints the Hermes recipe)
./scripts/install.sh
```

### The Hermes config recipe (the part that makes it live)

For **every** agent, set these (see the Hermes docs for exact key names):

```yaml
discord:
  free_response_channels: "<YOUR_CHANNEL_ID>"   # everyone sees every message
  allow_bots: mentions                          # agents answer each other when @mentioned
  no_thread_channels: "<YOUR_CHANNEL_ID>"       # replies land in the main channel, not threads
```

Then install the `war-room` skill (in `skills/war-room/`) into every agent and add
it to its preload list, so the discipline rule is always loaded.

Finally restart the gateways and post a message in the room.

### Running the bridge + watcher

```bash
./bridge.py                 # both loops, foreground
./watcher.py                # real-time wakeups

# or, as installed by install.sh:
systemctl --user enable --now war-room-bridge
systemctl --user enable --now war-room-watcher
```

## Configuration

See `config.example.toml` — it is fully commented. The three things you must set:

- `[discord]` — `guild_id`, `channel_id`, `owner_id` (your Discord user id).
- `[agents.<name>]` — one block per agent: its Discord `bot_id`, its Hermes
  `profile_dir`, and `name_only = true` if it has no Discord bot of its own.
- `[room].dir` — where `log.jsonl` lives (default `~/.fleet-room`).

## Message contract

One JSON line per message:

```json
{"id": "room-…", "from": "alice", "to": "bob", "thread": null,
 "kind": "note", "body": "…", "refs": [], "ts": "…"}
```

`kind` ∈ `question | answer | handoff | note | ack | raise`. Every message names a
`to` (`"*"` = broadcast). Only the addressee replies; a `thread` binds a
conversation; nobody writes another agent's card.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design and the
decisions behind it.

## License

MIT — see [LICENSE](LICENSE).
