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
--doctor says why a brief is not shown: configuration, trust, the storage
folders with owner and mode, the index and its age, the last sync failure and
the payload sizes. It reads nothing from GitHub, changes nothing, and never
prints the key or other secrets.

Examples:
  hooks.py --print
  hooks.py --doctor
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
import storage  # noqa: E402

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
    """The prompt-hook state file, in a checked folder outside the project tree (see storage.py)."""
    private = storage.folder(storage.state_top(), storage.repo_folder(repo))
    return os.path.join(private, "prompt-state.json")


def load_state(repo):
    """Raises storage.StorageError when the state file is a symlink or not safe; unreadable JSON counts as empty."""
    text = storage.read_file(state_path(repo))
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def save_state(repo, state):
    sessions = sorted(state.items(), key=lambda kv: kv[1].get("seen", 0))[-50:]  # keep the newest sessions only
    storage.write_file(state_path(repo), json.dumps(dict(sessions)))


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


NOT_SHOWN = "gh-issues-manager: record brief not shown: %s. Run hooks.py --doctor."


class Unavailable(Exception):
    """The project is set up and trusted, but there is no brief to show."""


def run(event, data, budget):
    """The text a hook prints. Silent when the project is not set up or not trusted; one line when the brief fails."""
    found = configured()
    if found is None:
        return ""
    config, repo, hub = found
    try:
        return produce(event, data, budget, config, repo, hub)
    except Unavailable as error:
        reason = str(error)
    except storage.StorageError as error:
        reason = "the local storage was refused (%s)" % error
    except Exception as error:  # noqa: BLE001 - a hook never fails a session
        reason = "an unexpected %s" % type(error).__name__
    line = NOT_SHOWN % reason
    if event == "session-start":
        return line
    if event == "subagent-start":
        return json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": line}})
    return ""


def produce(event, data, budget, config, repo, hub):
    fresh, failure = None, ""
    if event == "session-start":
        try:
            index.sync(repo, hub, timeout=max(2, budget // 3), deadline=max(2, budget - 2), timeline_cap=10,
                       log=lambda *a: None)
            fresh = True
        except storage.StorageError:
            raise
        except Exception as error:  # noqa: BLE001 - the cached index is used
            fresh = False
            failure = "GitHub could not be read (%s)" % ("timed out" if "timed out" in str(error) else
                                                         "gh failed" if isinstance(error, ghim.GhError) else
                                                         type(error).__name__)
    db = index.connect(repo, create=False)  # raises for an index that must not be read
    if db is None or not index.get_meta(db, "synced_at"):
        if db is not None:
            db.close()
        raise Unavailable("there is no local index yet%s" % (" and " + failure if failure else
                                                              "; the next session start fills it"))
    try:
        if failure:
            index.set_meta(db, "last_sync_error", "%s at %s" % (failure, index.now_utc()))
            db.commit()
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
    except (OSError, storage.StorageError):
        pass


def print_all():
    config = ghim.load_config()
    repo = ghim.resolve_repo(None, config)
    print(ghim.describe(config, repo))
    if repo.lower() not in ghim.trusted_repos():
        print("note: %s is not in your trusted repositories (%s), so the hooks print nothing for it; the payloads "
              "below show what they would print once it is trusted." % (repo, ghim.trusted_file()))
    try:
        db = index.connect(repo, create=False)
    except storage.StorageError as error:
        sys.exit("error: %s" % error)
    if db is None:
        sys.exit("error: no index for %s at %s; run index.py sync first" % (repo, index.index_path(repo)))
    total = 0
    for name, text in brief.all_payloads(db, config, repo).items():
        print("===== %s (%s): %d characters, cap %d =====" % (name, HOOK_NAMES[name], len(text), brief.CAPS[name]))
        print(text)
        total += len(text)
    print("===== total: %d characters =====" % total)
    return 0


def doctor():
    """Print what the hooks depend on. Returns 1 when something keeps the brief from being shown."""
    import shutil
    problems = []
    try:
        config = ghim.load_config()
    except (ValueError, OSError) as error:
        print("config: unreadable (%s)" % error)
        return 1
    print("config: %s" % (config.get("_path") or "none found at the project root (%s)" % ghim.project_root()))
    repo, hub = config.get("repo"), config.get("hub")
    print("repository: %s   hub: %s" % (repo or "not set", hub if hub is not None else "not set"))
    if not config.get("_path"):
        print("result: the hooks stay silent in this project because it is not set up")
        return 1
    if not (isinstance(repo, str) and "/" in repo and isinstance(hub, int)):
        print("result: the hooks stay silent because \"repo\" or \"hub\" is missing or malformed")
        return 1
    trusted = repo.lower() in ghim.trusted_repos()
    allowed = sorted(ghim.allowed_users(repo))
    print("trusted: %s (trusted list: %s; GHIM_TRUSTED_REPOS %s); allowed authors: %s"
          % ("yes" if trusted else "no", ghim.trusted_file(), "set" if os.environ.get("GHIM_TRUSTED_REPOS") else "not set",
             ", ".join(allowed) or "none"))
    if not trusted:
        problems.append("the repository is not trusted, so the hooks stay silent")
    gh = os.environ.get("GHIM_GH") or shutil.which("gh")
    print("gh: %s" % (gh.split()[0] if gh else "not found on PATH"))
    print("CLAUDE_PLUGIN_DATA: %s" % (os.environ.get("CLAUDE_PLUGIN_DATA") or "not set (XDG folders are used)"))
    name = storage.repo_folder(repo)
    rows = [("index top folder", storage.cache_top(), "top"),
            ("index private folder", os.path.join(storage.cache_top(), storage.PRIVATE), "private"),
            ("index folder", index.index_dir(repo), "private"),
            ("index file", index.index_path(repo), "file"),
            ("state top folder", storage.state_top(), "top"),
            ("state folder", os.path.join(storage.state_top(), storage.PRIVATE, name), "private"),
            ("prompt state file", os.path.join(storage.state_top(), storage.PRIVATE, name, "prompt-state.json"), "file"),
            ("key top folder", storage.state_top(for_key=True), "top"),
            ("key file (contents not shown)", storage.key_path(), "file")]
    seen = set()
    for label, path, kind in rows:
        if (path, kind) in seen:
            continue
        seen.add((path, kind))
        exists, owner, mode, problem = storage.describe(path)
        note = problem
        if exists and not problem and mode:
            bits = int(mode, 8)
            if kind == "top" and bits & 0o077:
                note = "loose; tightened to 700 on next use" if owner else note
            elif kind in ("private", "file") and bits & 0o077:
                note = "permissions for group or others: refused"
                problems.append("%s %s is mode %s" % (label, path, mode))
        if problem and problem != "missing":
            problems.append("%s %s: %s" % (label, path, problem))
        print("  %-30s %s  %s" % (label, path, ("owner %s, mode %s%s" % (owner, mode, ", " + note if note else ""))
                                  if exists else "missing"))
    try:
        db = index.connect(repo, create=False, tighten=False)
    except storage.StorageError as error:
        db = None
        problems.append("index refused: %s" % error)
        print("index: refused (%s)" % error)
    else:
        if db is None:
            problems.append("no index yet; a session start or `index.py sync` makes it")
            print("index: none yet")
    if db is not None:
        synced = index.get_meta(db, "synced_at")
        print("index: synced %s (%s)%s; %s" % (synced or "never", index.age_text(synced),
                                               "" if index.get_meta(db, "sync_complete") != "0" else ", incomplete",
                                               ", ".join("%s %d" % item for item in index.describe_index(db).items())))
        failure = index.get_meta(db, "last_sync_error")
        print("last sync failure: %s" % (failure or "none since the last good sync"))
        print("resume block: %s" % (index.get_meta(db, "resume_note") or "not read"))
        if synced:
            for event, text in brief.all_payloads(db, config, repo).items():
                print("payload %-15s %5d characters (cap %d)" % (event, len(text), brief.CAPS[event]))
        else:
            problems.append("the index was never filled")
        db.close()
    for problem in problems:
        print("problem: %s" % problem)
    print("result: %s" % ("the hooks can show the brief" if not problems else "%d problem(s) above" % len(problems)))
    return 1 if problems else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("event", nargs="?", choices=EVENTS)
    parser.add_argument("--print", action="store_true", help="show every payload and its size")
    parser.add_argument("--doctor", action="store_true", help="say why the brief is or is not shown; changes nothing")
    args = parser.parse_args(argv)
    if args.doctor:
        return doctor()
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
