#!/usr/bin/env bash
# war-room installer — writes config.toml (from the example), installs systemd
# user units for the bridge + watcher, and prints the Hermes config recipe.
#
# Safe to re-run: it never overwrites your existing config.toml.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3 || true)"

if [[ -z "$PY" ]]; then
  echo "error: python3 not found on PATH (need 3.11+)" >&2
  exit 1
fi

echo "war-room installer"
echo "  repo:   $REPO_DIR"
echo "  python: $PY ($($PY --version 2>&1))"
echo

# ── 1. config ────────────────────────────────────────────────────────────────
if [[ ! -f "$REPO_DIR/config.toml" ]]; then
  cp "$REPO_DIR/config.example.toml" "$REPO_DIR/config.toml"
  echo "✓ created config.toml — EDIT IT before running (Discord ids + agent roster)"
else
  echo "✓ config.toml already exists (left untouched)"
fi
echo

# ── 2. systemd user units ─────────────────────────────────────────────────────
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$SYSTEMD_DIR"

cat > "$SYSTEMD_DIR/war-room-bridge.service" <<EOF
[Unit]
Description=war-room bridge (Discord <-> disk room)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$PY "$REPO_DIR/bridge.py"
WorkingDirectory=$REPO_DIR
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

cat > "$SYSTEMD_DIR/war-room-watcher.service" <<EOF
[Unit]
Description=war-room watcher (real-time wakeups)
After=network-online.target

[Service]
Type=simple
ExecStart=$PY "$REPO_DIR/watcher.py"
WorkingDirectory=$REPO_DIR
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
echo "✓ installed war-room-bridge.service + war-room-watcher.service"
echo
echo "  Start them with:"
echo "    systemctl --user enable --now war-room-bridge war-room-watcher"
echo

# ── 2b. multiple rooms (optional) ─────────────────────────────────────────────
# To run an extra sealed room, copy the bridge unit and add Environment= lines
# (see config.example.toml "Multiple rooms" for the full list). Example for a
# private "ops" room with alice + bob only:
#
#   ROOM_CHANNEL_ID=<ops channel id> ROOM_LOG_NAME=ops ROOM_STATE_PREFIX=ops \
#   ROOM_AGENTS=alice,bob POLL_TOKEN_AGENT=alice \
#   systemctl --user enable --now war-room-bridge-ops
#
# Each extra room gets its OWN log (<room.dir>/ops.jsonl) and its OWN cursors,
# so it is fully sealed from the main room.
echo "  (optional) one systemd unit per extra room — see config.example.toml"
echo

# ── 3. Hermes config recipe ───────────────────────────────────────────────────
cat <<'RECIPE'
===============  HERMES CONFIG RECIPE  ================
For EACH agent, set in its config.yaml:

  discord.free_response_channels: "<channel_id>"   # everyone sees every message
  discord.allow_bots: mentions                     # agents answer each other when @mentioned
  discord.no_thread_channels: "<channel_id>"       # replies in the main channel

Then install skills/war-room/ into each agent and add "war-room"
to its skills.preload list. Restart the gateways, then post in
the room.
=====================================================
RECIPE
