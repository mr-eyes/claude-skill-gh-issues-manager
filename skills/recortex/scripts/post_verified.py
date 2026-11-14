#!/usr/bin/env python3
"""Post one comment, or replace one issue body, with lint and read-back.

comment: lints the draft, posts it with `gh issue comment --body-file`, fetches
the stored comment from the API and compares it with the draft.

body: lints the draft, prints a diff against the body now on GitHub, saves the
old body to a backup file, edits the issue and reads it back. Use it when what
the deliverable says changes: the draft is the whole new text, with no folded
old text. For a final record the issue must be labeled final-record (not hub
or active), and the section labels then follow the headings: the labels of new
sections are added, those of removed sections are removed (only with
--allow-label-removal), and the labels are read back. To convert a body of an
older form and keep it as a comment, use convert_body.py.

Examples:
  post_verified.py comment --issue 12 --kind result --body-file .tmp/result.md --dry-run
  post_verified.py comment --issue 12 --kind decision --body-file .tmp/decision.md
  post_verified.py body --issue 12 --kind final-record --body-file .tmp/topic.md --backup .tmp/topic-12.before.md --dry-run
"""

import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recortex  # noqa: E402
import lint_drafts  # noqa: E402


def lint(path, text, kind, repo, config, offline, labels=None, profiles=None):
    cache = {}

    def checker(number):
        if number not in cache:
            cache[number] = recortex.number_exists(repo, number)
        return cache[number]

    findings = lint_drafts.lint_text(text, kind=kind, config=config, labels=labels, profiles=profiles,
                                     number_checker=None if offline else checker)
    return lint_drafts.report(path, findings)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("comment", "body"):
        p = sub.add_parser(name)
        p.add_argument("--repo", help="owner/name (default: from .recortex.json)")
        p.add_argument("--issue", type=int, required=True, help="issue or pull request number")
        p.add_argument("--body-file", required=True, help="the one draft file to post")
        p.add_argument("--kind", required=True, choices=sorted(lint_drafts.KINDS), help="kind of draft, for lint")
        p.add_argument("--dry-run", action="store_true", help="lint and print the gh command; nothing is written")
        p.add_argument("--offline", action="store_true",
                       help="with --dry-run: no network access at all (bare #N is not checked)")
        if name == "body":
            p.add_argument("--backup", help="file that receives the body being replaced (required unless --dry-run)")
            p.add_argument("--profile", help="comma-separated profiles that define a final record's section "
                           "headings (default: profiles in .recortex.json)")
            p.add_argument("--allow-label-removal", action="store_true",
                           help="let the run remove section labels whose sections the body no longer has")
            p.add_argument("--allow-other-profiles", action="store_true",
                           help="go on although the issue carries section labels of other profiles; they are left alone")
    args = parser.parse_args(argv)
    if args.offline and not args.dry_run:
        parser.error("--offline only makes sense with --dry-run")

    config = recortex.load_config()
    repo = recortex.resolve_repo(args.repo, config)
    print(recortex.describe(config, repo))
    if not os.path.isfile(args.body_file):
        sys.exit("error: not a file: %s" % args.body_file)
    draft = recortex.read_text(args.body_file)
    chosen = getattr(args, "profile", None)
    profiles = [p.strip() for p in chosen.split(",") if p.strip()] if chosen else list(config.get("profiles") or [])
    follow = args.command == "body" and args.kind == "final-record" and not args.offline
    plan = None
    if follow:
        try:
            plan = recortex.plan_section_labels(recortex.read_issue(repo, args.issue)["labels"], draft, profiles)
        except ValueError as error:
            sys.exit("error: %s" % error)
        for reason in plan["stop"]:
            print("not posted: %s#%d: %s" % (repo, args.issue, reason))
        if plan["stop"]:
            return 1
        if plan["foreign"] and not args.allow_other_profiles:
            print("not posted: %s#%d carries section labels of profiles not in use here (%s; profiles in use: %s). "
                  "Pass --profile with the profiles of those labels, or --allow-other-profiles to leave them as they are"
                  % (repo, args.issue, ", ".join(plan["foreign"]), ", ".join(profiles) or "none"))
            return 1
    wanted = plan["wanted"] if plan and plan["checked"] and not plan["problems"] else None
    if lint(args.body_file, draft, args.kind, repo, config, args.offline, labels=wanted, profiles=profiles):
        print("not posted: fix the errors above")
        return 1

    if args.command == "comment":
        command = ["issue", "comment", str(args.issue), "--repo", repo, "--body-file", args.body_file]
        if args.dry_run:
            print("would run: " + recortex.show_command(command, "%d characters" % len(draft)))
            print("would read back: gh api repos/%s/issues/comments/<id> and compare with %s" % (repo, args.body_file))
            return 0
        url = recortex.gh(command).strip().split("\n")[-1]
        print("posted: %s" % url)
        match = re.search(r"#issuecomment-([0-9]+)", url)
        if not match:
            print("MISMATCH: could not find the comment id in gh output, so the comment was not read back")
            return 1
        ok = recortex.verify_body(draft, recortex.read_comment_body(repo, match.group(1)), "comment %s" % url)
        return 0 if ok else 1

    command = ["issue", "edit", str(args.issue), "--repo", repo, "--body-file", args.body_file]
    if args.dry_run and args.offline:
        print("would run: " + recortex.show_command(command, "%d characters" % len(draft)))
        if args.kind == "final-record":
            print("section labels not checked: --offline reads nothing from GitHub")
        return 0
    labels_command = None
    if follow and plan["checked"]:
        add, remove = plan["add"], plan["remove"]
        if add:
            have = {l["name"].lower() for l in json.loads(recortex.gh(
                ["label", "list", "--repo", repo, "--json", "name", "--limit", "1000"]))}
            missing = [label for label in add if label.lower() not in have]
            if missing:
                print("not posted: these labels do not exist in %s: %s; run setup_labels.py first"
                      % (repo, ", ".join(missing)))
                return 1
        if remove:
            print("removes: %s (the body has no section for %s)"
                  % (", ".join(remove), "it" if len(remove) == 1 else "them"))
            if not args.dry_run and not args.allow_label_removal:
                print("not posted: check that each of those sections left the deliverable on purpose, then rerun "
                      "with --allow-label-removal")
                return 1
        if add or remove:
            labels_command = recortex.label_command(repo, args.issue, add, remove)
    old = recortex.read_issue_body(repo, args.issue)
    diff = list(difflib.unified_diff(recortex.normalize(old).split("\n"), recortex.normalize(draft).split("\n"),
                                     "%s#%d now" % (repo, args.issue), args.body_file, lineterm=""))
    if not diff and not labels_command:
        print("no change: %s#%d already matches %s" % (repo, args.issue, args.body_file))
        return 0
    print("\n".join(diff))
    if args.dry_run:
        if diff:
            print("would run: " + recortex.show_command(command, "%d characters" % len(draft)))
        if labels_command:
            print("would run: " + recortex.show_command(labels_command, "section labels follow the headings"))
            if plan["remove"] and not args.allow_label_removal:
                print("note: the real run removes section labels only with --allow-label-removal")
        elif follow and not plan["checked"]:
            print("section labels not checked: no profile defines any")
        return 0
    if not diff:
        return follow_labels(repo, args.issue, labels_command, plan, profiles)
    if not args.backup:
        sys.exit("error: --backup FILE is required so the replaced body is kept")
    if os.path.exists(args.backup):
        sys.exit("error: backup file exists and is not overwritten: %s" % args.backup)
    with open(args.backup, "w", encoding="utf-8") as handle:
        handle.write(old)
    print("backup of the replaced body: %s" % args.backup)
    recortex.gh(command)
    print("ran: " + recortex.show_command(command))
    ok = recortex.verify_body(draft, recortex.read_issue_body(repo, args.issue), "%s#%d" % (repo, args.issue))
    if not ok:
        return 1
    return follow_labels(repo, args.issue, labels_command, plan, profiles) if follow else 0


def follow_labels(repo, number, command, plan, profiles):
    """Apply the section-label change, read the labels back and compare."""
    if not plan["checked"]:
        print("section labels not checked: no profile defines any")
        return 0
    wanted = plan["wanted"]
    if command:
        recortex.gh(command)
        print("ran: " + recortex.show_command(command))
    now = recortex.read_issue(repo, number)["labels"]
    add, remove = recortex.label_changes(now, wanted, profiles)
    if add or remove:
        print("MISMATCH: labels of %s#%d read back as %s; still to add: %s; still to remove: %s"
              % (repo, number, ", ".join(now) or "none", ", ".join(add) or "none", ", ".join(remove) or "none"))
        return 1
    print("verified: section labels of %s#%d follow the headings (%s)" % (repo, number, ", ".join(wanted) or "none"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except recortex.GhError as error:
        sys.exit("error: %s" % error)
