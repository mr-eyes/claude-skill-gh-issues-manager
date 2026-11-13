#!/usr/bin/env python3
"""Catch a project up when the record starts after months of work, or after a stretch without it.

inventory  Read-only. Lists what exists, with dates and sizes: git history
           (commits, tags, branches), merged pull requests and issues on
           GitHub (read-only; --offline skips them), project documents
           (README, CHANGELOG, CLAUDE.md, docs/, notes/), result and figure
           folders, and, only with --transcripts, the local Claude Code
           session transcripts and memory files of this project (listed by
           path, date and size; this script reads none of their contents).
           Writes <out>.json and <out>.md.
gap        Read-only. Commits, merged pull requests and changed files after the
           newest recorded event in the local index (or --since), for a backfill
           of work done while the record was not kept.
event      Writes one reconstructed event comment draft: the original time in
           the heading and marker, the time it is recorded, and its dated
           source. Only an event with a dated source is drafted; a decision
           without the decider's recorded words is written as "Decision
           inferred from <source>", never as a quote.

Nothing here posts. Drafts go through the usual review and post_verified.py.

Examples:
  catchup.py inventory --out .tmp/catchup/inventory
  catchup.py inventory --out .tmp/catchup/inventory --transcripts
  catchup.py gap
  catchup.py event --type result --at 2025-11-04T16:20:00+01:00 --title "first benchmark" \\
      --source commit:4f2a9c1 --body-file .tmp/catchup/notes-4f2a9c1.md --out .tmp/catchup/drafts/event-01.md
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghim  # noqa: E402
import lint_drafts  # noqa: E402
import record_format  # noqa: E402

DOCUMENTS = ("README", "CHANGELOG", "NEWS", "HISTORY", "CLAUDE.md", "NOTES", "TODO")
DOC_FOLDERS = ("docs", "notes", "doc")
RESULT_FOLDERS = ("results", "figures", "figs", "plots", "output", "out", "reports")
SKIP = {".git", "node_modules", ".tmp", "__pycache__", ".venv", "venv", "env", ".tox"}
SOURCE = re.compile(r"(commit|pr|issue|file|transcript):[\w./#:@+-]{1,200}")
TYPES = ("result", "decision", "failure", "checkpoint", "correction")


def stamp(seconds):
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git(root, *args):
    result = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True, timeout=120)
    return result.stdout if result.returncode == 0 else ""


def files_under(root, folder, depth=3, limit=2000):
    """(relative path, modified, size) of files under root/folder, at most `depth` levels and `limit` files."""
    out = []
    base = os.path.join(root, folder)
    if not os.path.isdir(base) or os.path.islink(base):
        return out
    stack = [(base, 0)]
    while stack and len(out) < limit:
        current, level = stack.pop()
        try:
            names = sorted(os.listdir(current))
        except OSError:
            continue
        for name in names:
            if name in SKIP:
                continue
            path = os.path.join(current, name)
            if os.path.islink(path):
                continue
            if os.path.isdir(path):
                if level + 1 < depth:
                    stack.append((path, level + 1))
                continue
            try:
                info = os.stat(path)
            except OSError:
                continue
            out.append((os.path.relpath(path, root), stamp(info.st_mtime), info.st_size))
            if len(out) >= limit:
                break
    return out


def transcripts_folder(root):
    """Where Claude Code keeps the session transcripts of the project at `root`."""
    encoded = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(root))
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", encoded)


def inventory(root, repo, offline, transcripts):
    data = {"root": root, "taken": stamp(datetime.datetime.now().timestamp()), "repo": repo}
    commits = []
    for line in git(root, "log", "--date=iso-strict", "--format=%H%x09%ad%x09%an%x09%s", "-n", "5000").splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            commits.append({"commit": parts[0], "date": parts[1], "author": parts[2], "subject": parts[3]})
    data["commits"] = commits
    data["tags"] = [dict(zip(("tag", "date"), line.split("\t", 1))) for line in git(
        root, "tag", "--list", "--format=%(refname:short)%09%(creatordate:iso-strict)").splitlines() if "\t" in line]
    data["branches"] = [dict(zip(("branch", "date"), line.split("\t", 1))) for line in git(
        root, "branch", "--format=%(refname:short)%09%(committerdate:iso-strict)").splitlines() if "\t" in line]
    data["pull_requests"], data["issues"] = [], []
    if repo and not offline:
        try:
            data["pull_requests"] = json.loads(ghim.gh(["pr", "list", "--repo", repo, "--state", "merged", "--json",
                                                        "number,title,mergedAt,url", "--limit", "1000"]) or "[]")
            data["issues"] = json.loads(ghim.gh(["issue", "list", "--repo", repo, "--state", "all", "--json",
                                                 "number,title,createdAt,closedAt,url", "--limit", "1000"]) or "[]")
        except (ghim.GhError, ValueError) as error:
            data["github_error"] = str(error)[:300]
    documents = []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        path = os.path.join(root, name)
        if os.path.isfile(path) and not os.path.islink(path) and name.upper().startswith(
                tuple(d.upper() for d in DOCUMENTS)):
            info = os.stat(path)
            documents.append((name, stamp(info.st_mtime), info.st_size))
    for folder in DOC_FOLDERS:
        documents += files_under(root, folder)
    data["documents"] = [{"path": p, "modified": m, "size": s} for p, m, s in documents]
    results = []
    for folder in RESULT_FOLDERS:
        results += files_under(root, folder)
    data["results"] = [{"path": p, "modified": m, "size": s} for p, m, s in results]
    data["transcripts"] = None
    if transcripts:
        folder = transcripts_folder(root)
        listed = []
        if os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                path = os.path.join(folder, name)
                if name.endswith(".jsonl") and os.path.isfile(path):
                    info = os.stat(path)
                    listed.append({"path": path, "modified": stamp(info.st_mtime), "size": info.st_size})
            memory = os.path.join(folder, "memory")
            if os.path.isdir(memory):
                for name in sorted(os.listdir(memory)):
                    path = os.path.join(memory, name)
                    if name.endswith(".md") and os.path.isfile(path):
                        info = os.stat(path)
                        listed.append({"path": path, "modified": stamp(info.st_mtime), "size": info.st_size})
        data["transcripts"] = listed
    return data


def summary(data):
    def span(rows, key):
        dates = sorted(r[key] for r in rows if r.get(key))
        return "%s to %s" % (dates[0][:10], dates[-1][:10]) if dates else "none"

    lines = ["# Inventory of %s" % data["root"], "", "Taken %s. Read-only; nothing was posted." % data["taken"], "",
             "| What | Count | Dates |", "|---|---|---|",
             "| Commits | %d | %s |" % (len(data["commits"]), span(data["commits"], "date")),
             "| Tags | %d | %s |" % (len(data["tags"]), span(data["tags"], "date")),
             "| Branches | %d | %s |" % (len(data["branches"]), span(data["branches"], "date")),
             "| Merged pull requests | %d | %s |" % (len(data["pull_requests"]), span(data["pull_requests"], "mergedAt")),
             "| Issues | %d | %s |" % (len(data["issues"]), span(data["issues"], "createdAt")),
             "| Documents | %d | %s |" % (len(data["documents"]), span(data["documents"], "modified")),
             "| Result and figure files | %d | %s |" % (len(data["results"]), span(data["results"], "modified")),
             "| Transcripts and memory files | %s | %s |" % (
                 "not read (no --transcripts)" if data["transcripts"] is None else len(data["transcripts"]),
                 span(data["transcripts"] or [], "modified"))]
    if data.get("github_error"):
        lines += ["", "GitHub could not be read: issues and pull requests are missing from this inventory."]
    lines += ["", "Next: propose the hub and the topic map from this inventory and have the user approve it before "
                  "anything is posted (references/catch-up.md)."]
    return "\n".join(lines) + "\n"


def newest_event(repo):
    import index
    try:
        db = index.connect(repo, create=False)
    except Exception:  # noqa: BLE001 - no usable index means no lower bound
        return None
    if db is None:
        return None
    try:
        rows = [r["at"] for r in db.execute("SELECT at FROM events WHERE type IN "
                                            "('result', 'decision', 'failure', 'checkpoint', 'correction')")]
    finally:
        db.close()
    keys = sorted((index.sort_key(at), at) for at in rows if at)
    return keys[-1][0] if keys else None


def gap(root, repo, since, offline):
    out = {"since": since, "commits": [], "pull_requests": [], "files": []}
    args = ["log", "--date=iso-strict", "--format=%H%x09%ad%x09%s"] + (["--since", since] if since else ["-n", "200"])
    for line in git(root, *args).splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            out["commits"].append({"commit": parts[0], "date": parts[1], "subject": parts[2]})
    if since:
        out["files"] = sorted({f for f in git(root, "log", "--since", since, "--name-only", "--format=").splitlines() if f})
    if repo and not offline:
        try:
            merged = json.loads(ghim.gh(["pr", "list", "--repo", repo, "--state", "merged", "--json",
                                         "number,title,mergedAt,url", "--limit", "500"]) or "[]")
            out["pull_requests"] = [p for p in merged if not since or (p.get("mergedAt") or "") > since]
        except (ghim.GhError, ValueError) as error:
            out["github_error"] = str(error)[:300]
    return out


def render_event(kind, at, title, source, body, now=None):
    """The text of a reconstructed event comment, or raise ValueError naming what is missing."""
    if kind not in TYPES:
        raise ValueError("type must be one of %s" % ", ".join(TYPES))
    if not re.fullmatch(record_format.ISO, at or ""):
        raise ValueError("--at must be the original time in ISO 8601 with its offset, for example 2025-11-04T16:20:00+01:00")
    if not SOURCE.fullmatch(source or ""):
        raise ValueError("--source must be commit:<hash>, pr:<number>, issue:<number>, file:<path> or transcript:<path>")
    if not title or not ghim.HEADING_TEXT.fullmatch(title):
        raise ValueError("--title must be plain text, at most 60 characters")
    original = datetime.datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
    recorded = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    marker = "<!-- ghim:event type=%s at=%s recorded=%s source=%s -->" % (
        kind, original.strftime("%Y-%m-%dT%H:%M:%SZ"), recorded, source)
    heading = "### %s (reconstructed): %s - %s" % (kind.capitalize(), original.strftime("%Y-%m-%d %H:%M UTC"), title)
    text = body.strip("\n")
    if kind == "decision" and not any(line.lstrip().startswith(">") for line in text.split("\n")) and \
            "decision inferred from" not in text.lower():
        text = "Decision inferred from %s; the decider's words were not recorded.\n\n%s" % (source, text)
        text = re.sub(r"^\*\*Exact words:\*\*\s*$", "**Exact words:** Not recorded; decision inferred from %s." % source,
                      text, count=1, flags=re.M)
    note = ("Reconstructed: recorded %s from %s. The time above is the time of the source, not of this comment."
            % (recorded, source))
    return "%s\n%s\n\n%s\n\n%s\n" % (marker, heading, note, text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="owner/name (default: from .gh-issues-manager.json, if any)")
    parser.add_argument("--root", help="project folder (default: the project root)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inventory")
    p.add_argument("--out", required=True, help="path without extension; .json and .md are written")
    p.add_argument("--offline", action="store_true", help="do not read issues and pull requests from GitHub")
    p.add_argument("--transcripts", action="store_true",
                   help="also list this project's local Claude Code transcripts and memory files (the user opted in)")
    p = sub.add_parser("gap")
    p.add_argument("--since", help="ISO time (default: the newest recorded event in the local index)")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("event")
    p.add_argument("--type", required=True, choices=TYPES)
    p.add_argument("--at", required=True, help="original time, ISO 8601 with offset")
    p.add_argument("--title", required=True)
    p.add_argument("--source", required=True, help="commit:<hash>, pr:<n>, issue:<n>, file:<path> or transcript:<path>")
    p.add_argument("--body-file", required=True, help="the facts of the event, with numbers and their sources")
    p.add_argument("--out", required=True, help="the draft file to write")
    args = parser.parse_args(argv)

    config = ghim.load_config()
    root = os.path.abspath(args.root or ghim.project_root())
    repo = args.repo or config.get("repo")
    if repo and not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        sys.exit("error: --repo must be owner/name")
    if args.command == "inventory":
        data = inventory(root, repo, args.offline, args.transcripts)
        folder = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(folder, exist_ok=True)
        with open(args.out + ".json", "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=1)
        with open(args.out + ".md", "w", encoding="utf-8") as handle:
            handle.write(summary(data))
        print(summary(data))
        print("wrote: %s.json and %s.md" % (args.out, args.out))
        return 0
    if args.command == "gap":
        since = args.since or (newest_event(repo) if repo else None)
        found = gap(root, repo, since, args.offline)
        if args.json:
            print(json.dumps(found, indent=1))
            return 0
        print("since: %s" % (since or "no recorded event; the newest 200 commits are listed"))
        print("commits: %d; merged pull requests: %d; changed files: %d" % (
            len(found["commits"]), len(found["pull_requests"]), len(found["files"])))
        for row in found["commits"][:200]:
            print("  commit %s %s %s" % (row["commit"][:12], row["date"], row["subject"][:100]))
        for row in found["pull_requests"]:
            print("  pull request #%s %s %s" % (row.get("number"), row.get("mergedAt"), str(row.get("title"))[:100]))
        return 0
    try:
        text = render_event(args.type, args.at, args.title, args.source, ghim.read_text(args.body_file))
    except (ValueError, OSError) as error:
        sys.exit("error: %s" % error)
    findings = [f for f in lint_drafts.lint_text(text, kind=args.type, config=config) if f.level == "error"]
    if lint_drafts.report(args.out, findings, quiet=True):
        print("not written: fill the body so that it passes the %s template's checks, then run again" % args.type)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    if os.path.exists(args.out):
        sys.exit("error: %s exists; drafts are not overwritten" % args.out)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(text)
    print("wrote: %s" % args.out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ghim.GhError as error:
        sys.exit("error: %s" % error)
