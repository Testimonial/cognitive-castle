#!/usr/bin/env bash
set -euo pipefail

# Records all 4 demo GIFs in one invocation.
#
# Prereqs (install all of these first):
#   vhs         — go install github.com/charmbracelet/vhs@latest
#   ttyd        — brew install ttyd  (or build from source)
#   asciinema   — brew install asciinema
#   agg         — brew install agg
#   expect      — brew install expect (or apt install expect)
#   castle      — pip install -e ".[dev]"  (this repo, editable)
#   claude      — Claude Code CLI, authenticated
#   JetBrains Mono — install system-wide (optional, VHS falls back)

cd "$(dirname "$0")/.."

# 1. Create a tiny demo source directory
rm -rf /tmp/castle-demo-src /tmp/castle-demo-palace
mkdir -p /tmp/castle-demo-src
cat > /tmp/castle-demo-src/README.md <<'EOF'
# myapp
A small demo project for Cognitive Castle.
EOF
cat > /tmp/castle-demo-src/auth.md <<'EOF'
# Auth flow

Auth flow uses JWT bearer tokens via the /api/auth endpoint.
Sessions expire after 24 hours.
EOF
cat > /tmp/castle-demo-src/decisions.md <<'EOF'
# Decisions

GraphQL replaced REST in Q3 because the client needed nested fetching.
EOF

# 2. Pre-warm the embedder (so vhs sees fast timings)
echo "Pre-warming embedder…"
castle init /tmp/castle-demo-src --palace /tmp/castle-demo-palace --yes >/dev/null 2>&1 || true
rm -rf /tmp/castle-demo-palace

# 3. Record demos 1-3 via vhs
echo "Recording demo 1 (hero)…"
vhs assets/demos/01-hero.tape

echo "Recording demo 2 (quickstart)…"
vhs assets/demos/02-quickstart.tape

echo "Recording demo 3 (verbatim)…"
vhs assets/demos/03-verbatim.tape

echo "Demos 1-3 done."

# 4. Record demo #4 via expect-driven claude session
# This burns Anthropic API tokens. Each regen ≈ a few cents.
echo "Recording demo #4 (MCP in Claude Code via expect)…"
echo "  -- this burns API tokens. Ctrl-C now if you don't want that."
sleep 3
./assets/demos/04-mcp.expect

echo
echo "✓ All 4 demos rendered to assets/demos/0X-name.gif"
du -h assets/demos/*.gif
