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
when there is no index yet, or on any error, with two exceptions of fixed
wording: at session start in the top folder of a git checkout with a GitHub
remote and no .gh-issues-manager.json, one line offers to set up the record,
once per project (off with GHIM_DISCOVERY=0 or "discovery": false in
~/.config/gh-issues-manager/settings.json); and in a project that is set up and
trusted, one line says why the brief is not shown. Nothing here writes to GitHub.

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


class OutOfTime(BaseException):
    """Raised by the alarm; a BaseException so that no `except Exception` inside the sync swallows it."""


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
    if not ghim.valid_repo(repo) or isinstance(hub, bool) or \
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
        return discovery() if event == "session-start" else ""
    config, repo, hub = found
    try:
        return produce(event, data, budget, config, repo, hub)
    except Unavailable as error:
        reason = str(error)
    except storage.StorageError as error:
        reason = "the local storage was refused (%s)" % STORAGE_REASONS.get(getattr(error, "kind", ""),
                                                                            "a storage folder or file is not safe to use")
    except Exception as error:  # noqa: BLE001 - a hook never fails a session
        reason = "an unexpected %s" % type(error).__name__
    line = NOT_SHOWN % reason
    if event == "session-start":
        return line
    if event == "subagent-start":
        return json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": line}})
    return ""


DISCOVERY = ("gh-issues-manager is installed, and this project has no record yet. Ask to set up the record (a few "
             "questions), or to catch up on earlier work. This line is shown once per project.")
SIGNAL = ("gh-issues-manager: the project now has %s (%s), a deliverable the setup does not cover. Ask the user once "
          "whether to add it with setup.py apply.")
SIGNAL_WORDS = {"paper": "paper or manuscript files", "thesis": "thesis files", "software": "software files",
                "dataset": "dataset files", "report": "analysis files", "prototype": "prototype files",
                "proposal": "proposal files", "docs": "documentation files"}


def discovery_off():
    if os.environ.get("GHIM_DISCOVERY", "").strip().lower() in ("0", "off", "no", "false"):
        return True
    try:
        with open(os.path.join(ghim.config_home(), "gh-issues-manager", "settings.json"), encoding="utf-8") as handle:
            return json.load(handle).get("discovery") is False
    except (OSError, ValueError, AttributeError):
        return False


def discovery():
    """One fixed line, once per project, for a git repository with a GitHub remote and no setup. No network; no
    project file is read (git reports the remotes)."""
    import subprocess
    if ghim.find_config() or discovery_off():
        return ""
    root = os.path.realpath(ghim.project_root())
    try:
        top = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             timeout=3).stdout.strip()
        if not top or os.path.realpath(top) != root:
            return ""  # only the top folder of a git checkout is a project here
        remotes = subprocess.run(["git", "-C", root, "config", "--get-regexp", r"^remote\..*\.url$"],
                                 capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if "github.com" not in remotes:
        return ""
    private = storage.folder(storage.state_top(for_key=True))
    path = os.path.join(private, "discovery.json")
    try:
        seen = json.loads(storage.read_file(path) or "{}")
    except ValueError:
        seen = {}
    seen = {k: v for k, v in seen.items() if re.fullmatch(r"[0-9a-f]{16}", k) and isinstance(v, (int, float))} \
        if isinstance(seen, dict) else {}
    key = digest(root)
    if key in seen:
        return ""
    seen[key] = time.time()
    storage.write_file(path, json.dumps(seen))
    return DISCOVERY


def new_signal(repo, config, room):
    """One fixed line naming a deliverable that files now suggest and the setup does not cover, once per kind. The
    line is optional: any failure (a malformed setup, refused storage, an unreadable folder) gives no line, and the
    brief is shown as usual."""
    try:
        import setup
        path = setup.told_path(repo)
        told = setup.read_told(path)
        covered = setup.covered_profiles(config)
        pending = {kind for kind, (profile, _) in setup.KINDS.items()
                   if kind in SIGNAL_WORDS and kind not in told and profile not in covered}
        if not pending:
            return ""  # every kind is covered or already mentioned: the project folder is not looked at
        for item in setup.uncovered_signals(os.path.realpath(ghim.project_root()), config):
            if item["kind"] not in pending:
                continue
            line = SIGNAL % (SIGNAL_WORDS[item["kind"]], ", ".join(e for e in item["evidence"] if re.fullmatch(
                r"[\w ./*-]{1,40}", e))[:120])
            if len(line) + 1 > room:
                return ""
            storage.write_file(path, json.dumps(told + [item["kind"]]))
            return line
    except Exception:  # noqa: BLE001 - the line is optional; the brief does not depend on it
        return ""
    return ""


BUILDING = ("gh-issues-manager: record brief not shown: building the local index in the background (first run); "
            "the brief appears at your next prompt. Run hooks.py --doctor for status.")
REBUILDING = ("gh-issues-manager: record brief not shown: the local index was refused (often a key that differs between "
              "environments, such as a terminal and a hook with another XDG_STATE_HOME or HOME); it is moved aside and "
              "rebuilt in the background, and the brief appears at your next prompt. Run hooks.py --doctor for status.")
# Fixed sentences for the notice: the error messages themselves hold paths from the environment and stay in --doctor.
STORAGE_REASONS = {
    "symlink": "a storage folder or file is a symlink",
    "owner": "a storage folder or file belongs to another user",
    "permissions": "a storage folder or file has permissions for group or others",
    "parent": "the storage folder is in a folder that others can write to",
    "not-folder": "a storage path is not the kind of file expected",
    "key": "the plugin's key is empty or damaged",
    "changed": "the index changed while it was being opened",
    "name": "the repository name cannot be used as a folder name",
    "lock": "the sync lock could not be taken",
}


def open_usable(repo):
    """(index or None, refused). Raises storage.StorageError for unsafe storage."""
    try:
        db = index.connect(repo, create=False)
    except index.RefusedIndex:
        return None, True  # a sync moves it aside and builds a new one
    if db is not None and not index.get_meta(db, "synced_at"):
        db.close()
        return None, False
    return db, False


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
    db, refused = open_usable(repo)
    fresh, failure = None, ""
    if event == "session-start":
        if db is None:
            building = index.running(repo)  # a file being written by a running build is not a refused index
            start_background(repo, config)
            remember(repo, session, None, brief=False)
            return REBUILDING if refused and not building else BUILDING
        db.close()
        if index.running(repo):
            fresh = None  # a background sync is writing the index; use it as it is
        else:
            share = max(1.0, budget / 2.0)  # the sync gets half the budget; the rest is for the brief
            try:
                with alarm(share + max(1.0, budget / 4.0)):  # a safety net; the sync stops itself at `share`
                    summary = index.sync(repo, hub, timeout=share, deadline=share, timeline_cap=10, log=lambda *a: None)
                fresh = True
                if not summary["complete"]:
                    if summary.get("pages"):
                        fresh = "partial"  # part was read; the rest continues in the background
                        failure = "more to read than fits in a session start; continuing in the background"
                    else:
                        fresh = False  # GitHub did not answer in time; nothing was read
                        failure = "GitHub could not be read (timed out)"
                    start_background(repo, config)  # a large backlog catches up without blocking sessions
            except storage.StorageError:
                raise
            except index.SyncBusy:
                fresh = None  # another sync holds the lock; use the index as it is
            except (Exception, OutOfTime) as error:  # noqa: BLE001 - the cached index is used
                fresh = False
                slow = isinstance(error, OutOfTime) or "timed out" in str(error) or "deadline" in str(error)
                failure = "GitHub could not be read (%s)" % ("timed out" if slow else "gh failed"
                                                             if isinstance(error, ghim.GhError) else
                                                             type(error).__name__)
                if slow:
                    start_background(repo, config)
        db, refused = open_usable(repo)
        if db is None:
            building = index.running(repo)
            start_background(repo, config)
            remember(repo, session, None, brief=False)
            return REBUILDING if refused and not building else BUILDING
    elif db is None:
        if event == "subagent-start" and index.running(repo):
            return json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": BUILDING}})
        if event == "prompt-submit":
            if not index.running(repo):
                start_background(repo, config)  # a build that was stopped or killed goes on; starting it is quick
            return ""
        raise Unavailable("there is no local index yet; the next session start builds it")
    try:
        if failure:
            index.set_meta(db, "last_sync_error", "%s at %s" % (failure, index.now_utc()))
            db.commit()
        record = brief.Record(db, config, repo)
        if event == "session-start":
            text = brief.session_payload(record, fresh)
            remember(repo, session, digest(record.key()), brief=True)
            signal = new_signal(repo, config, brief.CAPS["session-start"] - len(text))
            return text + ("\n" + signal if signal else "")
        if event == "subagent-start":
            return json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                                      "additionalContext": brief.subagent_payload(record)}})
        if event == "pre-compact":
            return brief.precompact_payload(record)
        settings = config.get("prompt_hook") if isinstance(config.get("prompt_hook"), dict) else {}
        every = settings.get("every") if isinstance(settings.get("every"), int) and settings.get("every") > 0 else 10
        key = digest(record.key())
        state = load_state(repo)
        entry = state.get(session, {"count": 0, "key": None})
        entry["count"] = entry.get("count", 0) + 1
        entry["seen"] = time.time()
        if entry.get("brief") is not True:
            # The session started without a brief (first build, or no SessionStart): give the full brief once,
            # also when the one-line reminder is switched off. Build the text first, then record that it was given.
            text = brief.session_payload(record, None)
            entry.update(brief=True, key=key)
            state[session] = entry
            save_state(repo, state)
            return text
        if settings.get("enabled") is False:
            state[session] = entry
            save_state(repo, state)
            return ""
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
    if not (ghim.valid_repo(repo) and isinstance(hub, int)):
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
    print("storage: index under %s, state and key under %s; hooks and terminal scripts resolve the same folders "
          "(CLAUDE_PLUGIN_DATA is not used)%s" % (storage.cache_top(), storage.state_top(for_key=True),
                                                 "; GHIM_TESTING and GHIM_DATA_HOME are set (for tests only): index and state under %s"
                                                 % storage.test_home() if storage.test_home() else ""))
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
