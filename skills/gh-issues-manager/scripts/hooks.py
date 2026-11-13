#!/usr/bin/env python3
"""Hook entry point: print the record brief for one Claude Code hook event.

Events:
  session-start   syncs the index from GitHub within the hook's time limit, then
                  prints the record brief; if GitHub cannot be read it prints
                  the brief from the index and says how old it is
  subagent-start  prints a short brief for a subagent as JSON additionalContext
                  (index only, no network)
  prompt-submit   prints one or two lines from the index (no network), only when
                  they changed since the last time in this session or every
                  N prompts; off with "prompt_hook": {"enabled": false} in
                  .gh-issues-manager.json, N set with "every"
  pre-compact     prints instructions for the compaction summary (index only)

Every event prints nothing and exits 0 when the project has no
.gh-issues-manager.json, when its repository is not in the user's trusted list,
when there is no index yet, or on any error. Nothing here writes to GitHub.

--print shows the four payloads and their sizes, for the user to check.

Examples:
  hooks.py --print
  echo '{"session_id": "abc"}' | hooks.py prompt-submit
"""

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghim  # noqa: E402
import index  # noqa: E402
import brief  # noqa: E402

EVENTS = ("session-start", "subagent-start", "prompt-submit", "pre-compact")
HOOK_NAMES = {"session-start": "SessionStart", "subagent-start": "SubagentStart",
              "prompt-submit": "UserPromptSubmit", "pre-compact": "PreCompact"}


def read_input():
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def state_path(repo):
    return os.path.join(index.data_dir(repo), "prompt-state.json")


def load_state(repo):
    try:
        with open(state_path(repo), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(repo, state):
    sessions = sorted(state.items(), key=lambda kv: kv[1].get("seen", 0))[-50:]  # keep the newest sessions only
    path = state_path(repo)
    with open(path + ".part", "w", encoding="utf-8") as handle:
        json.dump(dict(sessions), handle)
    os.replace(path + ".part", path)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def configured():
    """(config, repo, hub) when the project is set up and trusted, else None."""
    config = ghim.load_config()
    repo, hub = config.get("repo"), config.get("hub")
    if not isinstance(repo, str) or "/" not in repo or not isinstance(hub, int):
        return None
    if repo.lower() not in ghim.trusted_repos():
        return None
    return config, repo, hub


def run(event, data, budget):
    found = configured()
    if found is None:
        return ""
    config, repo, hub = found
    fresh = False
    if event == "session-start":
        try:
            index.sync(repo, hub, timeout=max(2, budget // 3), deadline=max(2, budget - 2), timeline_cap=10,
                       log=lambda *a: None)
            fresh = True
        except Exception:  # noqa: BLE001 - a hook never fails a session; the cached index is used
            fresh = False
    db = index.connect(repo, create=False)
    if db is None:
        return ""
    try:
        if not index.get_meta(db, "synced_at"):
            return ""  # an index that was never filled says nothing
        record = brief.Record(db, config, repo)
        session = str(data.get("session_id") or "")
        if event == "session-start":
            text = brief.session_payload(record, fresh)
            remember(repo, session, digest(record.key()), injected=True)
            return text
        if event == "subagent-start":
            return json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                                      "additionalContext": brief.subagent_payload(record)}})
        if event == "pre-compact":
            return brief.precompact_payload(record)
        settings = config.get("prompt_hook") if isinstance(config.get("prompt_hook"), dict) else {}
        if settings.get("enabled") is False:
            return ""
        every = settings.get("every") if isinstance(settings.get("every"), int) and settings.get("every") > 0 else 10
        key = digest(record.key())
        state = load_state(repo)
        entry = state.get(session, {"count": 0, "key": None})
        entry["count"] = entry.get("count", 0) + 1
        show = entry.get("key") != key or entry["count"] % every == 0
        if show:
            entry["key"] = key
        entry["seen"] = entry["count"] + len(state)
        state[session] = entry
        save_state(repo, state)
        return brief.prompt_payload(record) if show else ""
    finally:
        db.close()


def remember(repo, session, key, injected):
    try:
        state = load_state(repo)
        entry = state.get(session, {"count": 0})
        if injected:
            entry["key"] = key
        entry["seen"] = entry.get("count", 0) + len(state)
        state[session] = entry
        save_state(repo, state)
    except OSError:
        pass


def print_all():
    config = ghim.load_config()
    repo = ghim.resolve_repo(None, config)
    print(ghim.describe(config, repo))
    if repo.lower() not in ghim.trusted_repos():
        print("note: %s is not in your trusted repositories (%s), so the hooks print nothing for it; the payloads "
              "below show what they would print once it is trusted." % (repo, ghim.trusted_file()))
    db = index.connect(repo, create=False)
    if db is None:
        sys.exit("error: no index for %s at %s; run index.py sync first" % (repo, index.index_path(repo)))
    total = 0
    for name, text in brief.all_payloads(db, config, repo).items():
        print("===== %s (%s): %d characters, cap %d =====" % (name, HOOK_NAMES[name], len(text), brief.CAPS[name]))
        print(text)
        total += len(text)
    print("===== total: %d characters =====" % total)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("event", nargs="?", choices=EVENTS)
    parser.add_argument("--print", action="store_true", help="show every payload and its size")
    args = parser.parse_args(argv)
    if args.print:
        return print_all()
    if not args.event:
        parser.error("name an event or pass --print")
    try:
        budget = int(os.environ.get("GHIM_HOOK_TIMEOUT", "10"))
    except ValueError:
        budget = 10
    try:
        text = run(args.event, read_input(), budget)
    except Exception:  # noqa: BLE001 - hooks are silent on any failure
        return 0
    if text:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
