#!/usr/bin/env python3
"""Save every issue, pull request and comment of a repository as local Markdown.

Use it to read the record when GitHub is unreachable, and to survey an older
tracker before a migration. Read-only on GitHub. Writes INDEX.md and one file
per issue under --out, replacing files from an earlier snapshot of the same
issues and deleting nothing.

Examples:
  snapshot.py --repo owner/name --out .tmp/issues-snapshot
  snapshot.py --repo owner/old-tracker --out .tmp/old-tracker --dry-run
"""

import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghim  # noqa: E402


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_issue(issue, comments, repo):
    kind = "pull request" if "pull_request" in issue else "issue"
    labels = ", ".join(l["name"] for l in issue.get("labels", [])) or "none"
    lines = [
        "# %s#%d %s" % (repo, issue["number"], issue["title"]),
        "",
        "| Field | Value |",
        "|---|---|",
        "| Type | %s |" % kind,
        "| State | %s |" % issue.get("state", "?"),
        "| Labels | %s |" % cell(labels),
        "| Author | %s |" % (issue.get("user") or {}).get("login", "?"),
        "| Created (UTC) | %s |" % issue.get("created_at", "?"),
        "| Updated (UTC) | %s |" % issue.get("updated_at", "?"),
        "| URL | %s |" % issue.get("html_url", "?"),
        "| Comments | %d |" % len(comments),
        "",
        "## Body",
        "",
        (issue.get("body") or "(empty)").replace("\r\n", "\n"),
        "",
    ]
    for index, comment in enumerate(comments, 1):
        lines += [
            "---",
            "",
            "## Comment %d of %d: %s, %s UTC" % (index, len(comments),
                                                 (comment.get("user") or {}).get("login", "?"),
                                                 comment.get("created_at", "?")),
            "",
            comment.get("html_url", ""),
            "",
            (comment.get("body") or "(empty)").replace("\r\n", "\n"),
            "",
        ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="owner/name (default: from .gh-issues-manager.json)")
    parser.add_argument("--out", required=True, help="folder for the snapshot")
    parser.add_argument("--dry-run", action="store_true", help="print the gh calls and the target folder; fetch and write nothing")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="seconds allowed for each of the two listing calls (default 1800; a tracker with "
                             "thousands of comments needs minutes)")
    args = parser.parse_args(argv)

    config = ghim.load_config()
    repo = ghim.resolve_repo(args.repo, config)
    issue_call = ["api", "--paginate", "repos/%s/issues?state=all&per_page=100" % repo]
    comment_call = ["api", "--paginate", "repos/%s/issues/comments?per_page=100" % repo]
    print(ghim.describe(config, repo))
    if args.dry_run:
        print("would run: " + ghim.show_command(issue_call, "read-only"))
        print("would run: " + ghim.show_command(comment_call, "read-only"))
        print("would write: %s/INDEX.md and %s/issues/<number>.md" % (args.out, args.out))
        return 0

    issues = ghim.parse_json_stream(ghim.gh(issue_call, timeout=args.timeout))
    comments = ghim.parse_json_stream(ghim.gh(comment_call, timeout=args.timeout))
    by_issue = {}
    for comment in comments:
        match = re.search(r"/issues/([0-9]+)$", comment.get("issue_url", ""))
        if match:
            by_issue.setdefault(int(match.group(1)), []).append(comment)
    for group in by_issue.values():
        group.sort(key=lambda c: c.get("created_at", ""))

    os.makedirs(os.path.join(args.out, "issues"), exist_ok=True)
    issues.sort(key=lambda i: i["number"])
    hub = config.get("hub") if config.get("repo") == repo else None
    rows = []
    for issue in issues:
        number = issue["number"]
        name = "issues/%05d.md" % number
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as handle:
            handle.write(render_issue(issue, by_issue.get(number, []), repo))
        labels = ", ".join(l["name"] for l in issue.get("labels", []))
        rows.append("| [%d](%s) | %s | %s | %s | %s | %s | %d |" % (
            number, name, "PR" if "pull_request" in issue else "issue", issue.get("state", "?"),
            cell(labels), cell(issue["title"]) + (" (hub)" if number == hub else ""),
            issue.get("updated_at", "?"), len(by_issue.get(number, []))))

    taken = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    index = [
        "# Snapshot of %s" % repo,
        "",
        "Taken %s. Issues and pull requests: %d. Comments: %d." % (taken, len(issues), len(comments)),
        "All times in this snapshot are UTC, as the API returns them. A snapshot is a copy; GitHub is the record.",
    ]
    if hub:
        index += ["", "Start with the hub: [issue %d](issues/%05d.md)." % (hub, hub)]
    index += ["", "| Number | Type | State | Labels | Title | Updated (UTC) | Comments |", "|---|---|---|---|---|---|---|"]
    with open(os.path.join(args.out, "INDEX.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(index + rows) + "\n")
    print("wrote %d issue files and INDEX.md to %s (%d comments)" % (len(issues), args.out, len(comments)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ghim.GhError as error:
        sys.exit("error: %s" % error)
