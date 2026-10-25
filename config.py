"""Hermes War Room config loader.

Reads ``config.toml`` (or the path in ``FLEET_ROOM_CONFIG``) and exposes resolved
runtime values. This is the single source of truth that ``room.py``, ``bridge.py``
and ``watcher.py`` all import, so there is exactly one place where paths, Discord
ids and the agent roster are defined.

Stdlib only — requires Python 3.11+ (``tomllib``).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

# Where the config lives. Default: config.toml next to this file.
CONFIG_PATH = Path(
    os.environ.get("FLEET_ROOM_CONFIG", Path(__file__).parent / "config.toml")
)


def _resolve(p: str) -> Path:
    """Expand ~ and return an absolute Path."""
    return Path(os.path.expanduser(os.path.expandvars(p)))


if not CONFIG_PATH.exists():
    raise SystemExit(
        f"config not found: {CONFIG_PATH}\n"
        "Copy config.example.toml to config.toml and fill in your values."
    )

_cfg = tomllib.loads(CONFIG_PATH.read_text())

# ── room ──────────────────────────────────────────────────────────────────────
ROOM_DIR = _resolve(_cfg.get("room", {}).get("dir", "~/.fleet-room"))
# Per-room identity (env-overridable): run ONE bridge instance per room, each
# with its own sealed log name, cursor prefix, and channel. The defaults below
# keep single-room behaviour identical to before.
LOG_NAME = os.environ.get("ROOM_LOG_NAME", "log")
STATE_PREFIX = os.environ.get("ROOM_STATE_PREFIX", "bridge")
LOG = ROOM_DIR / f"{LOG_NAME}.jsonl"
CARDS = ROOM_DIR / "cards"
SEEN = ROOM_DIR / "seen"
WAKE = ROOM_DIR / "wake"
LOCK = ROOM_DIR / "LOCK"

# bridge state files (namespaced by STATE_PREFIX so rooms don't clobber cursors)
LAST_DISCORD = ROOM_DIR / f"{STATE_PREFIX}.last_discord_id"
LAST_ROOM = ROOM_DIR / f"{STATE_PREFIX}.last_room_id"
POSTED_IDS = ROOM_DIR / f"{STATE_PREFIX}.posted_ids.json"
WATCHER_STATE = ROOM_DIR / "watcher.state"

# ── discord ───────────────────────────────────────────────────────────────────
_discord = _cfg.get("discord", {})
GUILD_ID = _discord.get("guild_id", "")
# Env override lets a second room point at a different channel without editing
# config.toml (a fleet can run several rooms off one config).
CHANNEL_ID = os.environ.get("ROOM_CHANNEL_ID") or _discord.get("channel_id", "")
OWNER_ID = _discord.get("owner_id", "")
OWNER_NAME = _discord.get("owner_name", "you")

API = "https://discord.com/api/v10"
UA = "hermes-war-room-bridge/1.0"

# ── hermes ────────────────────────────────────────────────────────────────────
HERMES_PROFILES_DIR = _resolve(
    _cfg.get("hermes", {}).get("profiles_dir", "~/.hermes/profiles")
)

# ── agents ────────────────────────────────────────────────────────────────────
# AGENTS: name -> {"bot_id": str|None, "profile_dir": str, "name_only": bool}
AGENTS: dict[str, dict] = {}
NAME_ONLY: set[str] = set()

for _name, _spec in (_cfg.get("agents", {}) or {}).items():
    _name = str(_name).lower()
    _name_only = bool(_spec.get("name_only", False))
    if _name_only:
        NAME_ONLY.add(_name)
    AGENTS[_name] = {
        "bot_id": _spec.get("bot_id") or None,
        "profile_dir": str(_spec.get("profile_dir") or _name),
        "name_only": _name_only,
    }

ALL_NAMES: set[str] = set(AGENTS)

# ── room-scoped roster (env-overridable) ──────────────────────────────────────
# ROOM_AGENTS is a comma-separated list of agent names allowed in THIS room
# (e.g. "einstein,newtonian,neo" for a private ops room). Empty = every agent.
# Each room instance scopes its own roster so a leak between rooms is impossible
# at the bridge belt, not just the Discord permission gate.
ROOM_AGENTS = [
    n.strip().lower()
    for n in os.environ.get("ROOM_AGENTS", "").split(",")
    if n.strip()
]
ROOM_AGENT_SET: set[str] = set(ROOM_AGENTS) if ROOM_AGENTS else set(AGENTS)
ROOM_ID_TO_NAME: dict[str, str] = {
    a["bot_id"]: name
    for name, a in AGENTS.items()
    if name in ROOM_AGENT_SET and a["bot_id"]
}
ROOM_NAME_ONLY: set[str] = NAME_ONLY & ROOM_AGENT_SET
ROOM_ALL_NAMES: set[str] = ROOM_AGENT_SET | ROOM_NAME_ONLY

# Whose token polls the channel. Must be a member of THIS room — a bot that has
# no access to the channel returns HTTP 403. Default: the first agent with a
# token in the room roster.
POLL_TOKEN_AGENT = os.environ.get("POLL_TOKEN_AGENT", "").strip().lower()

# bot user id -> agent name (for decoding @mentions)
ID_TO_NAME: dict[str, str] = {
    a["bot_id"]: name for name, a in AGENTS.items() if a["bot_id"]
}

# ── addressing ────────────────────────────────────────────────────────────────
BROADCAST_WORDS: set[str] = {"all", "everyone", "fleet", "crew", "room", "here"}


# ── token helper ──────────────────────────────────────────────────────────────
def load_token(agent: str) -> str | None:
    """Read DISCORD_BOT_TOKEN from the agent's Hermes profile .env, if any."""
    info = AGENTS.get(agent)
    if not info or info.get("name_only"):
        return None
    p = HERMES_PROFILES_DIR / info["profile_dir"] / ".env"
    if not p.exists():
        return None
    for line in p.read_text(errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("DISCORD_BOT_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


TOKENS: dict[str, str | None] = {a: load_token(a) for a in AGENTS}
