#!/usr/bin/env bash
# Copy all raw Claude Code session transcripts for this project into chat_logs/,
# including subagent transcripts (stored under <session-id>/subagents/).
# Re-run any time; files are overwritten with the latest version.
set -euo pipefail
SRC="$HOME/.claude/projects/-Users-edwardamoah-Documents-GitHub-wbg-evaluation"
DEST="$(cd "$(dirname "$0")" && pwd)"
rsync -a --include='*/' --include='*.jsonl' --include='*.meta.json' --exclude='*' --exclude='memory/' "$SRC"/ "$DEST"/
find "$DEST" -name '*.jsonl' -exec ls -la {} +
