#!/usr/bin/env bash
# agent-lanes one-line installer (macOS). Run it inside your project folder:
#   curl -fsSL https://raw.githubusercontent.com/maxt8203/agent-lanes/main/get.sh | bash
# Try the demo instead:
#   mkdir agent-lanes-demo && cd agent-lanes-demo && curl -fsSL https://raw.githubusercontent.com/maxt8203/agent-lanes/main/get.sh | bash -s -- --demo
set -euo pipefail
REPO="maxt8203/agent-lanes"
TARGET="$(pwd -P)"

say() { printf '%s\n' "$*"; }
fail() { printf '❌ %s\n' "$*" >&2; exit 1; }

[[ "$TARGET" != "$(cd ~ && pwd -P)" ]] || fail "You're in your home folder. Make or open a project folder first, e.g.:  mkdir my-app && cd my-app"
[[ "$(uname)" == "Darwin" ]] || say "Note: agent-lanes is built for macOS. Continuing anyway."

# Python: on a fresh Mac, /usr/bin/python3 is only a stub until Apple's developer tools are installed.
PYBIN="$(command -v python3 || true)"
if [[ -z "$PYBIN" ]] || { [[ "$PYBIN" == /usr/bin/python3 && "$(uname)" == "Darwin" ]] && ! xcode-select -p >/dev/null 2>&1; }; then
  fail "Python 3 is needed. Run:  xcode-select --install   (Apple's free developer tools, 5-10 min), then paste the install line again."
fi

if ! command -v claude >/dev/null; then
  if command -v brew >/dev/null; then
    say "⚠️  Claude Code isn't installed yet. Install it with:  brew install --cask claude-code   (then run 'claude' once to log in)"
  else
    say "⚠️  Claude Code isn't installed yet. See https://code.claude.com/docs/en/setup"
  fi
fi

# Get the kit (AGENT_LANES_SRC lets you install from a local copy instead).
if [[ -n "${AGENT_LANES_SRC:-}" ]]; then
  SRC="$AGENT_LANES_SRC"
else
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  say "Downloading agent-lanes…"
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP" \
    || fail "Download failed. Check your internet connection, or use Download ZIP on https://github.com/$REPO"
  SRC="$TMP/agent-lanes-main"
fi

# Questions need the keyboard, not the piped script.
if [[ -r /dev/tty ]] && { : < /dev/tty; } 2>/dev/null; then
  python3 "$SRC/install.py" "$TARGET" "$@" < /dev/tty
else
  python3 "$SRC/install.py" "$TARGET" "$@" < /dev/null
fi
