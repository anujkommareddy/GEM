#!/bin/bash
set -euo pipefail

# Only run in remote (web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Install gstack dependencies
if [ -d "$CLAUDE_PROJECT_DIR/.claude/skills/gstack" ]; then
  cd "$CLAUDE_PROJECT_DIR/.claude/skills/gstack"
  bun install
  bun run gen:skill-docs
  bun build --compile browse/src/cli.ts --outfile browse/dist/browse
  bun build --compile browse/src/find-browse.ts --outfile browse/dist/find-browse
fi
