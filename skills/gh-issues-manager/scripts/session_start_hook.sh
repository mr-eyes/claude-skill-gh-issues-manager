#!/usr/bin/env bash
# SessionStart hook: print the record brief (rules, hub, deliverable topics,
# active issues and the newest allowed resume block) so it re-enters context
# after startup, resume, clear, compaction and fork. Kept under this name for
# settings that point at it; run_hook.sh does the work.

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || exit 0
exec bash "$here/run_hook.sh" session-start
