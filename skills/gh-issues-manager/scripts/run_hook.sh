#!/usr/bin/env bash
# Run one gh-issues-manager hook: session-start, subagent-start, prompt-submit or pre-compact.
# The hook's JSON input arrives on stdin and is passed on. Plain stdout is what
# Claude Code adds to the context (SubagentStart prints JSON with
# additionalContext). It prints only for a project with .gh-issues-manager.json
# whose repository the user has trusted (see the README, "Security model"). Any
# failure (no config, no python3, offline, slow) prints nothing and exits 0, so
# a session is never blocked.

event="${1:-}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
cd "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || exit 0
limit="${GHIM_HOOK_TIMEOUT:-10}"   # seconds the Python side plans for: half for the sync, the rest for the brief
case "$limit" in ''|*[!0-9]*) limit=10;; esac   # digits only; never evaluated as an expression
case "$limit" in ????*) limit=10;; esac         # and short
limit=$((10#$limit))                            # base 10, so 08 and 09 are numbers
[ "$limit" -ge 1 ] || limit=10
[ "$limit" -le 15 ] || limit=15
export GHIM_HOOK_TIMEOUT="$limit"
# The safety net stays below each hook's timeout in hooks.json (SessionStart 20, SubagentStart 10,
# UserPromptSubmit 5, PreCompact 10). The background sync is detached and has its own deadline.
case "$event" in
  session-start) hard=$((limit + 3)) ;;
  prompt-submit) hard=4 ;;
  *) hard=8 ;;
esac

if command -v timeout >/dev/null 2>&1; then
  timeout "$hard" python3 "$here/hooks.py" "$event" 2>/dev/null
else
  python3 "$here/hooks.py" "$event" 2>/dev/null
fi
exit 0
