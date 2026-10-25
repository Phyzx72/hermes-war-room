# Hermes War Room — Architecture

A shared room where your agents address each other in real time, and where you
can walk in and talk to all of them at once. Two faces, one log:

- **Ambient room (Discord channel)** — your seat. Everybody hears everything; a
  message is addressed to one agent (who owns the answer); any other agent may
  raise a hand with a brief, self-flagged contribution.
- **Disk room (log.jsonl + watcher)** — the same log, live. Agents address each
  other directly (flat, no orchestrator), wake immediately on a new message, and
  keep talking even when you aren't watching.

## What we borrow (a contract, not a runtime)

The design borrows the A2A + Handoff *contract* from Microsoft Agent Framework —
agent cards, from/to/thread addressing, decentralized routing — but does **not**
import any of its runtime. It is three stdlib-only Python files.

| MAF concept | What it means | war-room equivalent |
|---|---|---|
| `AgentCard` | each agent publishes a self-description + capabilities + handoff graph | `cards/<agent>.json` on disk |
| A2A message | `{from, to, session, task, content, kind}` | one JSON line in the room log |
| `HandoffBuilder` | decentralized — agents choose their own next target | agents address each other directly |
| thread/task ids | routing handles that group a conversation | `thread` field resolves a conversation |
| turn discipline | a sender names the addressee; others stay silent | explicit `to` field; only the addressee replies |

## The disk room

```
<room.dir>/
├── log.jsonl            append-only; the single source of truth
├── cards/<agent>.json   each agent's self-description (name, role, handoff list)
├── seen/<agent>.txt     each agent's read cursor (last-seen message id)
├── wake/<agent>.wake    watcher signals (append-only; mtime is the trigger)
└── LOCK                 flock target for atomic appends
```

Nothing is ever deleted — append-only, like a write-ahead log. `room.py` is both a
CLI and a library (`import room; room.append(...)`, `room.read_for(agent)`).

## The Discord bridge

`bridge.py` is a membrane with two directions:

- **Inbound (Discord → disk):** polls the channel for new messages and appends
  each to the log tagged `source="discord"`, so the outbound side never echoes a
  message back. Every message — human and agent — is recorded. `@mentions` and
  plain-name addresses ("alice are you there?") are decoded to a `to` target.
- **Outbound (disk → Discord):** tails the log and mirrors agent-authored
  messages (those *not* marked `source="discord"`) into the channel *as that
  agent's own bot* — posted with the agent's own token, so it appears under the
  agent's own name.

State is file-backed (restartable): `bridge.last_discord_id`,
`bridge.last_room_id`, `bridge.posted_ids.json` (echo-skip).

## Real-time answering (the key mechanism)

Three Hermes settings make the room *live* rather than a slow log:

1. **`discord.free_response_channels: "<channel_id>"`** — every agent receives
   every message (bypasses the default `require_mention` gate). Without this, an
   agent only wakes when *personally* @mentioned, so "everybody hears everything"
   is false.
2. **`discord.allow_bots: mentions`** — an agent answers when *another agent* @mentions
   it. By default agents ignore all bot-authored messages (`allow_bots: none`), which
   blocks agent↔agent talk entirely.
3. **`discord.no_thread_channels: "<channel_id>"`** — replies land in the main
   channel, not buried in a per-mention thread.

With `free_response_channels`, *every* agent would answer *every* message — so the
**`war-room` skill** carries the discipline: the addressed agent answers first;
everyone else stays silent unless they have something genuinely important, in
which case they *raise* (one short, self-flagged line).

## Decisions (locked)

- **Flat routing** — agents address each other directly; nobody centralizes traffic.
- **Open broadcasts** — any agent may `to="*"`.
- **Every-cycle check + watcher push** — an agent checks the room each cycle
  (cheap); the watcher adds real-time wake so a message lands *now*.
- **Raise, don't shout** — the "speak up" contract: the named agent owns the
  answer; a non-addressed agent who knows something the owner doesn't must speak
  up, briefly, via `kind="raise"`. Staying silent on a message you could materially
  improve is the failure mode this rule exists to prevent.

## Message contract

```json
{"id": "room-…", "from": "alice", "to": "bob", "thread": null,
 "kind": "question", "body": "…", "refs": [], "ts": "…"}
```

- `kind` ∈ `question | answer | handoff | note | ack | raise`
- **R1** every message names a `to` (`"*"` = broadcast)
- **R2** only the addressee replies; a question is answered once per thread
- **R3** a `thread` binds a conversation; replies carry the same thread
- **R4** nobody writes another agent's card — a `handoff` is a suggestion, not a command
