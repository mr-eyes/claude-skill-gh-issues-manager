#!/usr/bin/env python3
"""Show or update the "Resume here" block of the hub issue.

The block sits between <!-- resume:start --> and <!-- resume:end --> in the hub
body. `show` prints it. `update` replaces it with the content of a file, leaves
the rest of the hub untouched, and reads the hub back to confirm.

Examples:
  resume_block.py show
  resume_block.py show --active
  resume_block.py update --file .tmp/resume.md --dry-run
  resume_block.py update --file .tmp/resume.md
"""

import argparse
import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghim  # noqa: E402
import lint_drafts  # noqa: E402

HOOK_LIMIT = 9000  # Claude Code stores hook context above 10,000 characters in a file


def show(args, config):
    repo = ghim.resolve_repo(args.repo, config)
    hub = ghim.resolve_hub(args.hub, config)
    body = ghim.read_issue_body(repo, hub, timeout=args.timeout)
    block = ghim.extract_resume_block(body)
    lines = ["Project hub: %s#%d  https://github.com/%s/issues/%d" % (repo, hub, repo, hub)]
    if block is None:
        lines.append("The hub has no readable resume block (markers missing or malformed). Read the hub itself.")
    else:
        lines += ["Resume block, read from GitHub just now:", "", block.strip()]
    if args.active:
        try:
            raw = ghim.gh(["issue", "list", "--repo", repo, "--label", "active", "--state", "open",
                           "--json", "number,title,updatedAt", "--limit", "50"], timeout=args.timeout)
            active = json.loads(raw)
            lines += ["", "Open issues labeled active: %d" % len(active)]
            lines += ["- #%d %s (updated %s)" % (i["number"], i["title"], i.get("updatedAt", "?")) for i in active]
        except (ghim.GhError, ValueError):
            lines += ["", "Open issues labeled active: not read (query failed)."]
    lines += ["",
              "The GitHub issues are the project record. Session memory is not. The resume protocol of the "
              "gh-issues-manager skill reads this block, then the open active issues, then the newest comments "
              "of the topics in play."]
    text = "\n".join(lines)
    if len(text) > HOOK_LIMIT:
        text = text[:HOOK_LIMIT] + "\n[truncated; read the hub for the rest]"
    print(text)
    return 0


def update(args, config):
    repo = ghim.resolve_repo(args.repo, config)
    hub = ghim.resolve_hub(args.hub, config)
    new_block = ghim.read_text(args.file)
    new_block = new_block.replace(ghim.RESUME_START, "").replace(ghim.RESUME_END, "").strip("\n")

    findings = lint_drafts.lint_resume_block(new_block)
    findings += [f for f in lint_drafts.lint_text(new_block, kind="generic", config=config) if f.level == "error"]
    if lint_drafts.report(args.file, findings, quiet=True):
        print("not posted: fix the errors above")
        return 1

    body = ghim.read_issue_body(repo, hub)
    old_block = ghim.extract_resume_block(body)
    if old_block is None:
        print("error: hub %s#%d has no well-formed resume markers; fix the hub body first" % (repo, hub))
        return 1
    start = body.index(ghim.RESUME_START) + len(ghim.RESUME_START)
    end = body.index(ghim.RESUME_END)
    new_body = body[:start] + "\n" + new_block + "\n" + body[end:]
    if len(new_body) > ghim.BODY_LIMIT:
        print("error: the hub would be %d characters, over the %d limit" % (len(new_body), ghim.BODY_LIMIT))
        return 1

    diff = list(difflib.unified_diff(old_block.split("\n"), new_block.split("\n"),
                                     "resume block now", "resume block new", lineterm=""))
    print("\n".join(diff) if diff else "resume block unchanged")
    command = ["issue", "edit", str(hub), "--repo", repo, "--body-file", "-"]
    if args.dry_run:
        print("would run: " + ghim.show_command(command, "hub body from stdin, %d characters; only the resume block changes" % len(new_body)))
        return 0
    if not diff:
        return 0
    ghim.gh(command, stdin=new_body)
    print("ran: " + ghim.show_command(command))
    return 0 if ghim.verify_body(new_body, ghim.read_issue_body(repo, hub), "hub %s#%d" % (repo, hub)) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("show", "update"):
        p = sub.add_parser(name)
        p.add_argument("--repo", help="owner/name (default: from .gh-issues-manager.json)")
        p.add_argument("--hub", type=int, help="hub issue number (default: from .gh-issues-manager.json)")
        if name == "show":
            p.add_argument("--active", action="store_true", help="also list open issues labeled active")
            p.add_argument("--timeout", type=int, default=30, help="seconds allowed per gh call")
            p.add_argument("--quiet-fail", action="store_true",
                           help="print nothing and exit 0 on any failure (for the SessionStart hook)")
        else:
            p.add_argument("--file", required=True, help="file holding the new block")
            p.add_argument("--dry-run", action="store_true", help="show the change without editing the hub")
    args = parser.parse_args(argv)
    quiet = getattr(args, "quiet_fail", False)
    try:
        config = ghim.load_config()
        if quiet and not ((args.repo or config.get("repo")) and (args.hub or config.get("hub"))):
            return 0
        return show(args, config) if args.command == "show" else update(args, config)
    except (ghim.GhError, ValueError, OSError) as error:
        if quiet:
            return 0
        sys.exit("error: %s" % error)


if __name__ == "__main__":
    sys.exit(main())
