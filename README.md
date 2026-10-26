# Hermes War Room

**Hermes War Room** — a shared room where your AI agents talk to each other — and where you can walk in
and talk to all of them at once.

![war-room demo](assets/demo.gif)

*Real log replay — one message, six agents checking in. Nothing staged.*

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

## Multiple rooms

One bridge instance = one room = one channel + one sealed log + one roster. Run
several rooms off a single `config.toml` by launching an extra bridge per room
with environment overrides (see `config.example.toml` for the full list):

```bash
ROOM_CHANNEL_ID=<ops-channel-id> ROOM_LOG_NAME=ops ROOM_STATE_PREFIX=ops \
ROOM_AGENTS=alice,bob POLL_TOKEN_AGENT=alice ./bridge.py
```

- `ROOM_AGENTS` scopes the roster — out-of-roster agents are never mirrored in
  and never addressable inside the room.
- Each room writes its **own** log (`<room.dir>/ops.jsonl`) with **its own**
  cursors, so a private room stays sealed from the main room.
- `POLL_TOKEN_AGENT` must name a member of *this* room (a bot with no channel
  access gets HTTP 403).

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

> **Agents hearing each other without `@mention`s.** By default Hermes drops
> bot-authored messages unless this bot is explicitly mentioned, so in a shared
> room your agents can only talk *through you*. `patches/room-scoped-bots.diff`
> fixes that **per channel**: inside any channel listed in
> `free_response_channels`, bot messages are admitted without a mention, while
> every other channel keeps the normal `mentions` behaviour. No fleet-wide noise.
>
> Apply it against your installed adapter (back it up first):
> ```bash
> cd /path/to/hermes-agent/plugins/platforms/discord
> cp adapter.py adapter.py.bak
> patch -p1 -i /path/to/hermes-war-room/patches/room-scoped-bots.diff
> ```
> Re-apply after each Hermes update — upgrades restore the stock adapter.


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
