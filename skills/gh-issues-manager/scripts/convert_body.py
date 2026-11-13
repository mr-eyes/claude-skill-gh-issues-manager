#!/usr/bin/env python3
"""Replace a topic issue's body with deliverable text, keeping the former body as a comment.

Use it to convert a record body of an older form into a body that is the
deliverable's text. Steps, in this order, each checked:

1. Check the issue: it must be labeled final-record and not hub or active, and
   carry no section labels of profiles other than the ones in use. Lint the
   new body as a final record and work out the section labels its headings
   call for. Stop on any error, when a label does not exist, or when a section
   label would be removed without --allow-label-removal.
2. Compare the live body with --expected, the copy the new text was drafted
   from. Stop when they differ: someone edited the issue in the meantime.
3. Post the former body, unchanged, as a comment headed "Record: former issue
   body, kept as history (not deliverable text)" with the --note sentence
   first, and read it back.
4. Check the live body once more, replace it with the new body, read it back.
   GitHub has no conditional edit of an issue body, so an edit made in the
   moment between this check and the replacement cannot be detected; the
   read-back and the issue's edit history show what happened.
5. Add the section labels of the new headings, remove the section labels of
   sections the body no longer has, and read the labels back. Role and topic
   labels are left alone.

--dry-run reads GitHub and prints the record comment, the diff and every
command; it writes nothing. A rerun after a failure continues: a record comment
by the same account that keeps the same former body is adopted instead of
posted again (whatever its note), and a body that already equals the new text
is not edited again.

Examples:
  convert_body.py --issue 12 --body-file drafts/topic-12.md --expected live/topic-12.md \\
      --note "Replaced on 2026-03-09 11:20 PST by the methods text, when the tracker moved to deliverable bodies." --dry-run
"""

import argparse
import datetime
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghim  # noqa: E402
import lint_drafts  # noqa: E402

RULE = "\n---\n\n"
MENTION = re.compile(r"(?<![\w`/@.])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\b")


def record_comment(note, former, at=None):
    """The comment that keeps a former body: event marker, heading, the note, a rule, the body unchanged."""
    body = former.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    at = at or datetime.datetime.now().astimezone().isoformat(timespec="minutes")
    marker = "<!-- ghim:event type=record at=%s -->" % at
    return "%s\n%s\n\n%s\n%s%s\n" % (marker, ghim.RECORD_HEADING, note.strip(), RULE, body)  # a blank line before the rule


def split_record(text):
    """(note, former body) of a record comment, with or without its event marker, or None when the text is not one."""
    text = ghim.normalize(text)
    first, _, rest = text.partition("\n")
    if first.startswith("<!-- ghim:event"):
        text = rest
    if not text.startswith(ghim.RECORD_HEADING + "\n") or RULE not in text:
        return None
    head, former = text.split(RULE, 1)
    return head[len(ghim.RECORD_HEADING):].strip(), former


def find_record(repo, number, former):
    """Record comments by this account on the issue that keep exactly this former body."""
    me = ghim.gh(["api", "user", "--jq", ".login"]).strip()
    rows = ghim.parse_json_stream(ghim.gh(
        ["api", "--paginate", "repos/%s/issues/%d/comments?per_page=100" % (repo, number)]))
    wanted = ghim.normalize(former.replace("\r\n", "\n").replace("\r", "\n").strip("\n"))
    found = []
    for row in rows:
        parts = split_record(row.get("body") or "")
        if (row.get("user") or {}).get("login") == me and parts and parts[1] == wanted:
            found.append((row, parts[0]))
    return found


def mentions(text):
    """@handles in prose that GitHub would notify, outside code spans and fenced blocks."""
    names = []
    for _, line, region in lint_drafts.split_regions(text.replace("\r\n", "\n")):
        if region == "prose":
            for name in MENTION.findall(lint_drafts.strip_inline_code(line)):
                if name not in names:
                    names.append(name)
    return names


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
    parser.add_argument("--allow-label-removal", action="store_true",
                        help="let the run remove section labels whose sections the new body no longer has")
    parser.add_argument("--allow-other-profiles", action="store_true",
                        help="go on although the issue carries section labels of other profiles; they are left as they are")
    parser.add_argument("--dry-run", action="store_true", help="read GitHub, print everything, write nothing")
    args = parser.parse_args(argv)

    config = ghim.load_config()
    repo = ghim.resolve_repo(args.repo, config)
    print(ghim.describe(config, repo))
    profiles = [p.strip() for p in args.profile.split(",") if p.strip()] if args.profile else \
        list(config.get("profiles") or [])
    for path in (args.body_file, args.expected):
        if not os.path.isfile(path):
            sys.exit("error: not a file: %s" % path)
    if not re.search(lint_drafts.STAMP, args.note):
        sys.exit("error: --note needs the date, time and zone of the change, for example 2026-03-09 11:20 PST")
    if "\n" in args.note.strip():
        sys.exit("error: --note is one sentence on one line")
    draft = ghim.read_text(args.body_file)
    expected = ghim.read_text(args.expected)

    # 1. The issue, the lint and the labels.
    issue = ghim.read_issue(repo, args.issue)
    try:
        plan = ghim.plan_section_labels(issue["labels"], draft, profiles)
    except ValueError as error:
        sys.exit("error: %s" % error)
    for reason in plan["stop"]:
        print("nothing changed: %s#%d: %s" % (repo, args.issue, reason))
    if plan["stop"]:
        return 1
    if plan["foreign"] and not args.allow_other_profiles:
        print("nothing changed: %s#%d carries section labels of profiles not in use here (%s; profiles in use: %s). "
              "Pass --profile with the profiles of those labels, or --allow-other-profiles to leave them as they are"
              % (repo, args.issue, ", ".join(plan["foreign"]), ", ".join(profiles) or "none"))
        return 1
    wanted, add, remove = plan["wanted"], plan["add"], plan["remove"]
    findings = lint_drafts.lint_text(draft, kind="final-record", config=config, profiles=profiles,
                                     labels=None if plan["problems"] else wanted,
                                     number_checker=lambda n: ghim.number_exists(repo, n))
    if lint_drafts.report(args.body_file, findings):
        print("nothing changed: fix the errors above")
        return 1
    if add:
        have = {l["name"].lower() for l in json.loads(ghim.gh(
            ["label", "list", "--repo", repo, "--json", "name", "--limit", "1000"]))}
        missing = [label for label in add if label.lower() not in have]
        if missing:
            print("nothing changed: these labels do not exist in %s: %s; run setup_labels.py first"
                  % (repo, ", ".join(missing)))
            return 1
    if remove:
        print("removes: %s (the new body has no section for %s)" % (", ".join(remove), "it" if len(remove) == 1 else "them"))
        if not args.dry_run and not args.allow_label_removal:
            print("nothing changed: check that each of those sections left the deliverable on purpose, then rerun "
                  "with --allow-label-removal")
            return 1

    live = issue["body"]
    done = ghim.normalize(live) == ghim.normalize(draft)
    comment = record_comment(args.note, live)
    found = []
    if done:
        print("body: %s#%d already holds %s; only the labels are checked" % (repo, args.issue, args.body_file))
    else:
        # 2. The live body must be the one the new text was drafted from.
        if ghim.normalize(live) != ghim.normalize(expected):
            print("stopped: the live body of %s#%d differs from %s at %s"
                  % (repo, args.issue, args.expected, ghim.first_difference(ghim.normalize(expected), ghim.normalize(live))))
            print("someone changed it since the copy was taken; save the live body again, redraft, and rerun")
            return 1
        found = find_record(repo, args.issue, live)
        if found:
            print("found, not posted again: a record comment that keeps this body is already on the issue: %s "
                  "(its note: %s)" % (found[0][0]["html_url"], found[0][1]))
        else:
            if len(comment) > ghim.BODY_LIMIT:
                print("nothing changed: the record comment would be %d characters, over GitHub's limit of %d. "
                      "Keep the former body by hand in two comments headed \"%s, part 1 of 2\" and \"part 2 of 2\" "
                      "(post_verified.py comment --kind generic), then replace the body with post_verified.py body; "
                      "see references/migration.md" % (len(comment), ghim.BODY_LIMIT, ghim.RECORD_HEADING[4:]))
                return 1
            lint_comment = [f for f in lint_drafts.lint_text(comment, config=config)
                            if f.level == "error" and f.code in ("secret", "restricted", "resume-markers-misplaced")]
            if lint_drafts.report("record comment", lint_comment, quiet=True):
                print("nothing changed: the former body cannot be posted as a comment as it is")
                return 1
            names = mentions(live)
            if names:
                print("warning: the former body mentions %s; the record comment notifies %s again. Mentions inside "
                      "backticks do not notify, but the record keeps the body unchanged"
                      % (", ".join("@" + n for n in names), "them" if len(names) > 1 else "that account"))
            print("record comment, %d characters:" % len(comment))
            print("\n".join("  | " + line for line in comment.rstrip("\n").split("\n")))
        diff = difflib.unified_diff(ghim.normalize(live).split("\n"), ghim.normalize(draft).split("\n"),
                                    "%s#%d now" % (repo, args.issue), args.body_file, lineterm="")
        print("\n".join(diff))

    body_command = ["issue", "edit", str(args.issue), "--repo", repo, "--body-file", args.body_file]
    labels_command = ghim.label_command(repo, args.issue, add, remove) if add or remove else None
    if args.dry_run:
        if not done:
            if not found:
                print("would run: " + ghim.show_command(["issue", "comment", str(args.issue), "--repo", repo,
                                                         "--body-file", "-"], "the record comment above"))
            print("would read back: the record comment, then check the live body again")
            print("would run: " + ghim.show_command(body_command, "%d characters" % len(draft)))
            print("would read back: gh api repos/%s/issues/%d and compare with %s" % (repo, args.issue, args.body_file))
        if not plan["checked"]:
            print("section labels not checked: no profile defines any")
        elif labels_command:
            print("would run: " + ghim.show_command(labels_command))
            if remove and not args.allow_label_removal:
                print("note: the real run removes section labels only with --allow-label-removal")
        else:
            print("labels: section labels already follow the headings (%s)" % (", ".join(wanted) or "none"))
        return 0

    if not done:
        # 3. Keep the former body as a comment, unless an earlier run already did.
        if found:
            # Adopted, possibly in another layout: read it back and check that it still keeps this former body.
            url = found[0][0]["html_url"]
            match = re.search(r"#issuecomment-([0-9]+)", url)
            parts = split_record(ghim.read_comment_body(repo, match.group(1))) if match else None
            if not parts or parts[1] != ghim.normalize(live.replace("\r\n", "\n").replace("\r", "\n").strip("\n")):
                print("stopped: the adopted record comment %s no longer keeps the former body; the body was not "
                      "replaced" % url)
                return 1
            print("verified: record comment %s keeps the former body" % url)
        else:
            url = ghim.gh(["issue", "comment", str(args.issue), "--repo", repo, "--body-file", "-"],
                          stdin=comment).strip().split("\n")[-1]
            print("posted: %s" % url)
            match = re.search(r"#issuecomment-([0-9]+)", url)
            if not match or not ghim.verify_body(comment, ghim.read_comment_body(repo, match.group(1)),
                                                 "record comment %s" % url):
                print("stopped: the record comment did not read back; the body was not replaced")
                return 1

        # 4. Replace the body, if it is still the one the record comment keeps.
        if ghim.normalize(ghim.read_issue_body(repo, args.issue)) != ghim.normalize(expected):
            print("stopped: the live body changed after the record comment was posted, so the body was not replaced. "
                  "The record comment %s says the body was replaced, which is not so: post a correction comment that "
                  "links to it, then save the live body again, redraft, and rerun" % url)
            return 1
        ghim.gh(body_command)
        print("ran: " + ghim.show_command(body_command))
        if not ghim.verify_body(draft, ghim.read_issue_body(repo, args.issue), "%s#%d" % (repo, args.issue)):
            return 1

    # 5. Section labels follow the headings.
    if not plan["checked"]:
        print("section labels not checked: no profile defines any")
        return 0
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
