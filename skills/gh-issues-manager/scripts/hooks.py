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
import contextlib
import hashlib
import json
import os
import re
import signal
import sys
import time

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
    def seen(item):
        value = item[1].get("seen", 0)
        return value if isinstance(value, (int, float)) else 0
    sessions = sorted(state.items(), key=seen)[-50:]  # keep the 50 sessions used most recently
    storage.write_file(state_path(repo), json.dumps(dict(sessions)))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class OutOfTime(Exception):
    pass


@contextlib.contextmanager
def alarm(seconds):
    """Interrupt the block after `seconds`, where the platform allows it, so a slow GitHub cannot eat the budget."""
    if not hasattr(signal, "setitimer"):
        yield
        return

    def ring(signum, frame):
        raise OutOfTime()

    previous = signal.signal(signal.SIGALRM, ring)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def configured():
    """(config, repo, hub) when the project is set up and trusted, else None."""
    config = ghim.load_config()
    repo, hub = config.get("repo"), config.get("hub")
    if not isinstance(repo, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or isinstance(hub, bool) or \
            not isinstance(hub, int) or hub < 1:
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


BUILDING = ("gh-issues-manager: record brief not shown: building the local index in the background (first run); "
            "the brief appears at your next prompt. Run hooks.py --doctor for status.")


def open_usable(repo):
    """The index when it can be used for a brief, else None. Raises storage.StorageError for unsafe storage."""
    try:
        db = index.connect(repo, create=False)
    except index.RefusedIndex:
        return None  # a sync moves it aside and builds a new one
    if db is not None and not index.get_meta(db, "synced_at"):
        db.close()
        return None
    return db


def start_background(repo, config):
    """Start the detached background sync unless one is running. Returns "started" or "running"."""
    import subprocess
    if index.running(repo):
        return "running"
    storage.folder(storage.cache_top(), storage.repo_folder(repo))
    budget = index.background_budget(config)
    if not index.take_lock(repo, budget):  # taken here, so a second hook sees it at once
        return "running"
    log = index.background_files(repo)["log"]
    index.log_line(repo, "starting background sync from a hook")
    descriptor = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        child = subprocess.Popen(
            [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.py"), "--repo", repo,
             "sync", "--background", "--lock-held", "--deadline", str(budget)],
            cwd=ghim.project_root(), stdin=subprocess.DEVNULL, stdout=descriptor, stderr=descriptor,
            start_new_session=True, close_fds=True)
    finally:
        os.close(descriptor)
    index.hand_lock(repo, child.pid, budget)
    return "started"


def produce(event, data, budget, config, repo, hub):
    session = str(data.get("session_id") or "")
    db = open_usable(repo)
    fresh, failure = None, ""
    if event == "session-start":
        if db is None:
            start_background(repo, config)
            remember(repo, session, None, brief=False)
            return BUILDING
        db.close()
        if index.running(repo):
            fresh = None  # a background sync is writing the index; use it as it is
        else:
            share = max(1.0, budget / 2.0)  # the sync gets half the budget; the rest is for the brief
            try:
                with alarm(share + 0.5):
                    summary = index.sync(repo, hub, timeout=share, deadline=share, timeline_cap=10, log=lambda *a: None)
                fresh = True
                if not summary["complete"]:
                    start_background(repo, config)  # a large backlog catches up without blocking sessions
            except storage.StorageError:
                raise
            except Exception as error:  # noqa: BLE001 - the cached index is used
                fresh = False
                slow = isinstance(error, OutOfTime) or "timed out" in str(error) or "deadline" in str(error)
                failure = "GitHub could not be read (%s)" % ("timed out" if slow else "gh failed"
                                                             if isinstance(error, ghim.GhError) else
                                                             type(error).__name__)
                if slow:
                    start_background(repo, config)
        db = open_usable(repo)
        if db is None:
            start_background(repo, config)
            remember(repo, session, None, brief=False)
            return BUILDING
    elif db is None:
        if event == "subagent-start" and index.running(repo):
            return json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": BUILDING}})
        raise Unavailable("there is no local index yet; the next session start builds it")
    try:
        if failure:
            index.set_meta(db, "last_sync_error", "%s at %s" % (failure, index.now_utc()))
            db.commit()
        record = brief.Record(db, config, repo)
        if event == "session-start":
            text = brief.session_payload(record, fresh)
            remember(repo, session, digest(record.key()), brief=True)
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
        entry["seen"] = time.time()
        if entry.get("brief") is not True:
            # The session started without a brief (first build, or no SessionStart): give the full brief once.
            entry.update(brief=True, key=key)
            state[session] = entry
            save_state(repo, state)
            return brief.session_payload(record, None)
        show = entry.get("key") != key or entry["count"] % every == 0
        if show:
            entry["key"] = key
        state[session] = entry
        save_state(repo, state)
        return brief.prompt_payload(record) if show else ""
    finally:
        db.close()


def remember(repo, session, key, brief):
    """Record in the session's state whether it got the full brief, and the fingerprint it saw."""
    try:
        state = load_state(repo)
        entry = state.get(session, {"count": 0})
        entry["brief"] = brief
        if brief:
            entry["key"] = key
        entry["seen"] = time.time()
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
        moved = index.get_meta(db, "moved_aside") if db is not None else ""
        if moved:
            print("an earlier index was refused and moved aside to %s" % moved)
        failure = index.get_meta(db, "last_sync_error")
        print("last sync failure: %s" % (failure or "none since the last good sync"))
        print("resume block: %s" % (index.get_meta(db, "resume_note") or "not read"))
        if synced:
            for event, text in brief.all_payloads(db, config, repo).items():
                print("payload %-15s %5d characters (cap %d)" % (event, len(text), brief.CAPS[event]))
        else:
            problems.append("the index was never filled")
        db.close()
    try:
        active, last, error_line = index.background_status(repo)
    except storage.StorageError as error:
        active, last, error_line = None, None, "unreadable: %s" % error
    if active:
        print("background sync: running (pid %d, started %s UTC, budget %d s)"
              % (int(active["pid"]), time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(active["started"])),
                 int(active["budget"])))
    else:
        print("background sync: not running")
    if last:
        print("last background sync: finished %s, %s" % (index.clean(last.get("finished"), 40),
                                                          index.clean(last.get("result"), 120)))
    else:
        print("last background sync: none recorded")
    if error_line:
        print("last error line of the sync log: %s" % index.clean(error_line, 300))
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
