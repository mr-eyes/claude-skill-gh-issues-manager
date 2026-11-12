#!/usr/bin/env python3
"""Post one comment, or replace one issue body, with lint and read-back.

comment: lints the draft, posts it with `gh issue comment --body-file`, fetches
the stored comment from the API and compares it with the draft.

body: lints the draft, prints a diff against the body now on GitHub, saves the
old body to a backup file, edits the issue and reads it back. Use it when a
conclusion changes: the draft carries the new current state plus the replaced
text in a folded <details> block.

Examples:
  post_verified.py comment --issue 12 --kind result --body-file .tmp/result.md --dry-run
  post_verified.py comment --issue 12 --kind decision --body-file .tmp/decision.md
  post_verified.py body --issue 12 --kind final-record --body-file .tmp/topic.md --backup .tmp/topic-12.before.md
"""

import argparse
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghim  # noqa: E402
import lint_drafts  # noqa: E402


def lint(path, text, kind, repo, config, offline):
    cache = {}

    def checker(number):
        if number not in cache:
            cache[number] = ghim.number_exists(repo, number)
        return cache[number]

    findings = lint_drafts.lint_text(text, kind=kind, config=config,
                                     number_checker=None if offline else checker)
    return lint_drafts.report(path, findings)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("comment", "body"):
        p = sub.add_parser(name)
        p.add_argument("--repo", help="owner/name (default: from .gh-issues-manager.json)")
        p.add_argument("--issue", type=int, required=True, help="issue or pull request number")
        p.add_argument("--body-file", required=True, help="the one draft file to post")
        p.add_argument("--kind", required=True, choices=sorted(lint_drafts.KINDS), help="kind of draft, for lint")
        p.add_argument("--dry-run", action="store_true", help="lint and print the gh command; nothing is written")
        p.add_argument("--offline", action="store_true",
                       help="with --dry-run: no network access at all (bare #N is not checked)")
        if name == "body":
            p.add_argument("--backup", help="file that receives the body being replaced (required unless --dry-run)")
    args = parser.parse_args(argv)
    if args.offline and not args.dry_run:
        parser.error("--offline only makes sense with --dry-run")

    config = ghim.load_config()
    repo = ghim.resolve_repo(args.repo, config)
    if not os.path.isfile(args.body_file):
        sys.exit("error: not a file: %s" % args.body_file)
    draft = ghim.read_text(args.body_file)
    if lint(args.body_file, draft, args.kind, repo, config, args.offline):
        print("not posted: fix the errors above")
        return 1

    if args.command == "comment":
        command = ["issue", "comment", str(args.issue), "--repo", repo, "--body-file", args.body_file]
        if args.dry_run:
            print("would run: " + ghim.show_command(command, "%d characters" % len(draft)))
            print("would read back: gh api repos/%s/issues/comments/<id> and compare with %s" % (repo, args.body_file))
            return 0
        url = ghim.gh(command).strip().split("\n")[-1]
        print("posted: %s" % url)
        match = re.search(r"#issuecomment-(\d+)", url)
        if not match:
            print("MISMATCH: could not find the comment id in gh output, so the comment was not read back")
            return 1
        ok = ghim.verify_body(draft, ghim.read_comment_body(repo, match.group(1)), "comment %s" % url)
        return 0 if ok else 1

    command = ["issue", "edit", str(args.issue), "--repo", repo, "--body-file", args.body_file]
    if args.dry_run and args.offline:
        print("would run: " + ghim.show_command(command, "%d characters" % len(draft)))
        return 0
    old = ghim.read_issue_body(repo, args.issue)
    diff = list(difflib.unified_diff(ghim.normalize(old).split("\n"), ghim.normalize(draft).split("\n"),
                                     "%s#%d now" % (repo, args.issue), args.body_file, lineterm=""))
    if not diff:
        print("no change: %s#%d already matches %s" % (repo, args.issue, args.body_file))
        return 0
    print("\n".join(diff))
    if args.dry_run:
        print("would run: " + ghim.show_command(command, "%d characters" % len(draft)))
        return 0
    if not args.backup:
        sys.exit("error: --backup FILE is required so the replaced body is kept")
    if os.path.exists(args.backup):
        sys.exit("error: backup file exists and is not overwritten: %s" % args.backup)
    with open(args.backup, "w", encoding="utf-8") as handle:
        handle.write(old)
    print("backup of the replaced body: %s" % args.backup)
    ghim.gh(command)
    print("ran: " + ghim.show_command(command))
    ok = ghim.verify_body(draft, ghim.read_issue_body(repo, args.issue), "%s#%d" % (repo, args.issue))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ghim.GhError as error:
        sys.exit("error: %s" % error)
