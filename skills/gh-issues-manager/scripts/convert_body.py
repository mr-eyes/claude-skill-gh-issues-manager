#!/usr/bin/env python3
"""Replace a topic issue's body with deliverable text, keeping the former body as a comment.

Use it to convert a record body of an older form into a body that is the
deliverable's text. Steps, in this order, each checked:

1. Lint the new body as a final record and work out the section labels its
   headings call for. Stop on any error, or when a label does not exist.
2. Compare the live body with --expected, the copy the new text was drafted
   from. Stop when they differ: someone edited the issue in the meantime.
3. Post the former body, unchanged, as a comment headed "Record: former issue
   body, kept as history (not deliverable text)" with the --note sentence
   first, and read it back.
4. Check the live body once more, replace it with the new body, read it back.
5. Add the section labels of the new headings, remove the section labels of
   sections the body no longer has, and read the labels back. Role and topic
   labels are left alone.

--dry-run reads GitHub and prints the record comment, the diff and every
command; it writes nothing. A rerun after a failure continues: a record comment
with the same text by the same account is adopted instead of posted again, and
a body that already equals the new text is not edited again.

Examples:
  convert_body.py --issue 12 --body-file drafts/topic-12.md --expected drafts/topic-12.live.md \\
      --note "Replaced on 2026-03-09 11:20 PST by the methods text, when the tracker moved to deliverable bodies." --dry-run
"""

import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghim  # noqa: E402
import lint_drafts  # noqa: E402


def record_comment(note, former):
    """The comment that keeps a former body: heading, the note, a rule, the body unchanged."""
    body = former.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    return "%s\n\n%s\n\n---\n\n%s\n" % (ghim.RECORD_HEADING, note.strip(), body)


def find_comment(repo, number, text):
    """Comments by this account on the issue whose text equals `text`."""
    me = ghim.gh(["api", "user", "--jq", ".login"]).strip()
    rows = ghim.parse_json_stream(ghim.gh(
        ["api", "--paginate", "repos/%s/issues/%d/comments?per_page=100" % (repo, number)]))
    return [row for row in rows if (row.get("user") or {}).get("login") == me
            and ghim.normalize(row.get("body") or "") == ghim.normalize(text)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="owner/name (default: from .gh-issues-manager.json)")
    parser.add_argument("--issue", type=int, required=True, help="the topic issue to convert")
    parser.add_argument("--body-file", required=True, help="the new body: deliverable text, linted as a final record")
    parser.add_argument("--expected", required=True,
                        help="the copy of the live body the new text was drafted from; the run stops if the live body differs")
    parser.add_argument("--note", required=True,
                        help="one sentence for the record comment saying when (date, time, zone) and why the body was replaced")
    parser.add_argument("--profile", help="comma-separated profiles that define the section headings "
                        "(default: profiles in .gh-issues-manager.json)")
    parser.add_argument("--dry-run", action="store_true", help="read GitHub, print everything, write nothing")
    args = parser.parse_args(argv)

    config = ghim.load_config()
    repo = ghim.resolve_repo(args.repo, config)
    print(ghim.describe(config, repo))
    profiles = [p.strip() for p in (args.profile or ",".join(config.get("profiles") or [])).split(",") if p.strip()]
    for path in (args.body_file, args.expected):
        if not os.path.isfile(path):
            sys.exit("error: not a file: %s" % path)
    if not re.search(lint_drafts.STAMP, args.note):
        sys.exit("error: --note needs the date, time and zone of the change, for example 2026-03-09 11:20 PST")
    if "\n" in args.note.strip():
        sys.exit("error: --note is one sentence on one line")
    draft = ghim.read_text(args.body_file)
    expected = ghim.read_text(args.expected)

    # 1. Lint and labels.
    issue = ghim.read_issue(repo, args.issue)
    try:
        wanted, problems = ghim.labels_from_headings(draft, profiles, intended=issue["labels"])
    except ValueError as error:
        sys.exit("error: %s" % error)
    findings = lint_drafts.lint_text(draft, kind="final-record", config=config, profiles=profiles,
                                     labels=None if problems else wanted,
                                     number_checker=lambda n: ghim.number_exists(repo, n))
    if lint_drafts.report(args.body_file, findings):
        print("nothing changed: fix the errors above")
        return 1
    add, remove = ghim.label_changes(issue["labels"], wanted, profiles)
    if add:
        have = {l["name"].lower() for l in json.loads(ghim.gh(
            ["label", "list", "--repo", repo, "--json", "name", "--limit", "1000"]))}
        missing = [label for label in add if label.lower() not in have]
        if missing:
            print("nothing changed: these labels do not exist in %s: %s; run setup_labels.py first"
                  % (repo, ", ".join(missing)))
            return 1

    live = issue["body"]
    done = ghim.normalize(live) == ghim.normalize(draft)
    comment = record_comment(args.note, live)
    if done:
        print("body: %s#%d already holds %s; only the labels are checked" % (repo, args.issue, args.body_file))
    else:
        # 2. The live body must be the one the new text was drafted from.
        if ghim.normalize(live) != ghim.normalize(expected):
            print("stopped: the live body of %s#%d differs from %s at %s"
                  % (repo, args.issue, args.expected, ghim.first_difference(ghim.normalize(expected), ghim.normalize(live))))
            print("someone changed it since the copy was taken; save the live body again, redraft, and rerun")
            return 1
        lint_comment = [f for f in lint_drafts.lint_text(comment, config=config)
                        if f.level == "error" and f.code in ("secret", "restricted", "length", "resume-markers-misplaced")]
        if lint_drafts.report("record comment", lint_comment, quiet=True):
            print("nothing changed: the former body cannot be posted as a comment as it is")
            return 1
        print("record comment, %d characters:" % len(comment))
        print("\n".join("  | " + line for line in comment.rstrip("\n").split("\n")))
        diff = difflib.unified_diff(ghim.normalize(live).split("\n"), ghim.normalize(draft).split("\n"),
                                    "%s#%d now" % (repo, args.issue), args.body_file, lineterm="")
        print("\n".join(diff))

    body_command = ["issue", "edit", str(args.issue), "--repo", repo, "--body-file", args.body_file]
    labels_command = ghim.label_command(repo, args.issue, add, remove) if add or remove else None
    if args.dry_run:
        if not done:
            print("would run: " + ghim.show_command(["issue", "comment", str(args.issue), "--repo", repo,
                                                     "--body-file", "-"], "the record comment above"))
            print("would read back: the record comment, then check the live body again")
            print("would run: " + ghim.show_command(body_command, "%d characters" % len(draft)))
            print("would read back: gh api repos/%s/issues/%d and compare with %s" % (repo, args.issue, args.body_file))
        if labels_command:
            print("would run: " + ghim.show_command(labels_command))
        else:
            print("labels: section labels already follow the headings (%s)" % (", ".join(wanted) or "none"))
        return 0

    if not done:
        # 3. Keep the former body as a comment, unless an earlier run already did.
        found = find_comment(repo, args.issue, comment)
        if found:
            url = found[0]["html_url"]
            print("found: the record comment is already on the issue, not posted again: %s" % url)
        else:
            url = ghim.gh(["issue", "comment", str(args.issue), "--repo", repo, "--body-file", "-"],
                          stdin=comment).strip().split("\n")[-1]
            print("posted: %s" % url)
        match = re.search(r"#issuecomment-(\d+)", url)
        if not match or not ghim.verify_body(comment, ghim.read_comment_body(repo, match.group(1)),
                                             "record comment %s" % url):
            print("stopped: the record comment did not read back; the body was not replaced")
            return 1

        # 4. Replace the body, if it is still the one the record comment keeps.
        if ghim.normalize(ghim.read_issue_body(repo, args.issue)) != ghim.normalize(expected):
            print("stopped: the live body changed after the record comment was posted; the body was not replaced. "
                  "The record comment stays; save the live body again, redraft, and rerun")
            return 1
        ghim.gh(body_command)
        print("ran: " + ghim.show_command(body_command))
        if not ghim.verify_body(draft, ghim.read_issue_body(repo, args.issue), "%s#%d" % (repo, args.issue)):
            return 1

    # 5. Section labels follow the headings.
    if labels_command:
        ghim.gh(labels_command)
        print("ran: " + ghim.show_command(labels_command))
    now = ghim.read_issue(repo, args.issue)["labels"]
    add, remove = ghim.label_changes(now, wanted, profiles)
    if add or remove:
        print("MISMATCH: labels of %s#%d read back as %s; still to add: %s; still to remove: %s"
              % (repo, args.issue, ", ".join(now) or "none", ", ".join(add) or "none", ", ".join(remove) or "none"))
        return 1
    print("verified: section labels of %s#%d follow the headings (%s)" % (repo, args.issue, ", ".join(wanted) or "none"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ghim.GhError as error:
        sys.exit("error: %s\nrerun the same command to continue; finished steps are not repeated" % error)
