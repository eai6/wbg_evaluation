#!/usr/bin/env bash
# Copy all raw Claude Code session transcripts for this project into chat_logs/,
# including subagent transcripts (stored under <session-id>/subagents/).
# Re-run any time; files are overwritten with the latest version.
# Main session logs are also written gzip-compressed (lossless: `gunzip -k` restores the identical file), because the
# raw transcript exceeds GitHub's 100 MB file limit; the raw top-level .jsonl files are git-ignored.
set -euo pipefail
SRC="$HOME/.claude/projects/-Users-edwardamoah-Documents-GitHub-wbg-evaluation"
DEST="$(cd "$(dirname "$0")" && pwd)"
rsync -a --include='*/' --include='*.jsonl' --include='*.meta.json' --exclude='*' --exclude='memory/' "$SRC"/ "$DEST"/
for f in "$DEST"/*.jsonl; do gzip -9 -n -c "$f" > "$f.gz"; done
find "$DEST" -name '*.jsonl*' -exec ls -la {} +
