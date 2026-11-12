#!/usr/bin/env bash
# SessionStart hook: print the hub's resume block so it re-enters context after
# startup, resume and compaction. Plain stdout from a SessionStart hook is added
# to the session context. Any failure (no config, no gh, offline, slow) prints
# nothing and exits 0, so a session is never blocked or delayed for long.

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
command -v gh >/dev/null 2>&1 || [ -n "${GHIM_GH:-}" ] || exit 0

cd "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || exit 0
limit="${GHIM_HOOK_TIMEOUT:-10}"

if command -v timeout >/dev/null 2>&1; then
  timeout "$limit" python3 "$here/resume_block.py" show --active --quiet-fail --timeout 4 </dev/null 2>/dev/null
else
  python3 "$here/resume_block.py" show --active --quiet-fail --timeout 4 </dev/null 2>/dev/null
fi
exit 0
