#!/usr/bin/env bash
set -euo pipefail
# Explicit escape hatch for tool/version checks; all flows go through the CLI.
case "${1:-}" in
  codex|glab|git|bash|python3) exec "$@" ;;
  *) exec python3 /opt/codex-glab/cli.py "$@" ;;
esac
