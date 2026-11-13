#!/usr/bin/env python3
"""Compile the deliverable and the dated history of the project from the record.

Read-only on GitHub. It first syncs the local index (index.py) unless
--no-sync is given, then writes, under --out:

  deliverable/NN-<label>.md   for each deliverable section, in the hub's order,
                              the text under that section's heading in every
                              topic body that carries the section label, in the
                              hub's topic order, each under a topic heading with
                              the issue link
  deliverable/figures.tsv     every figure block: id, issue, title, caption, image at its ref, data, command
  deliverable/tables.tsv      every table block, the same columns
  deliverable/sources.tsv     every row of every "Sources" section, with its topic
  history/timeline.tsv        every event comment of every issue in time order, with
  history/timeline.md         the issue events (opened, labeled, unlabeled, renamed,
                              closed, reopened, pinned) and body edits; a comment
                              that is not a typed event is kept with type "other"
  MANIFEST.json               repository, hub, time of compilation, counts, --ref

Files of the same name are replaced; nothing else in --out is touched.

Examples:
  compile.py --out .tmp/compiled --dry-run
  compile.py --out .tmp/compiled --ref v0.3.0
"""

import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghim  # noqa: E402
import index  # noqa: E402
import record_format  # noqa: E402

TIMELINE_COLUMNS = ["at", "type", "issue", "issue_title", "labels", "title", "author", "url", "recorded", "reconstructed"]
BLOCK_COLUMNS = ["id", "issue", "title", "section", "caption", "image", "ref", "path", "data", "command"]


def cell(value):
    return re.sub(r"[\t\r\n]+", " ", "" if value is None else str(value)).strip()


def write_tsv(path, columns, rows):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\t".join(columns) + "\n")
        for row in rows:
            handle.write("\t".join(cell(row.get(c)) for c in columns) + "\n")


def hub_order(db, hub, profiles):
    """[(label, heading, [issue numbers])] in the order of the hub's deliverable tables, then the rest by profile."""
    sections = ghim.section_labels(profiles)
    by_heading = {}
    for label, heading in sections:
        by_heading.setdefault(heading.lower(), []).append(label)
    labels_of = {}
    for row in db.execute("SELECT issue, label FROM labels"):
        labels_of.setdefault(row["issue"], set()).add(row["label"].lower())
    topics = sorted(n for n, ls in labels_of.items() if "final-record" in ls)
    order, members = [], {}

    def place(label, number):
        if label not in members:
            order.append(label)
            members[label] = []
        if number not in members[label]:
            members[label].append(number)

    hub_row = db.execute("SELECT body FROM issues WHERE number = ?", (hub or 0,)).fetchone()
    text = record_format.section_text(hub_row["body"] or "", "Deliverable sections") if hub_row else None
    for line in (text or "").split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
        if len(cells) < 2:
            continue
        found = re.search(r"#(\d+)", cells[1])
        candidates = by_heading.get(cells[0].lower(), [])
        if not found or not candidates:
            continue
        number = int(found.group(1))
        chosen = [l for l in candidates if l.lower() in labels_of.get(number, set())]
        if chosen:
            place(chosen[0], number)
    for label, heading in sections:
        for number in topics:
            if label.lower() in labels_of.get(number, set()):
                place(label, number)
    headings = dict(sections)
    return [(label, headings[label], members[label]) for label in order]


def build(db, config, repo, hub, out, ref=None, dry_run=False):
    profiles = config.get("profiles") or []
    plan = hub_order(db, hub, profiles)
    files = []
    issues = {r["number"]: r for r in db.execute("SELECT * FROM issues")}
    deliverable = os.path.join(out, "deliverable")
    history = os.path.join(out, "history")
    if not dry_run:
        os.makedirs(deliverable, exist_ok=True)
        os.makedirs(history, exist_ok=True)
    counts = {"sections": 0, "section_texts": 0, "figures": 0, "tables": 0, "sources": 0, "events": 0,
              "timeline_rows": 0, "other_comments": 0}
    for position, (label, heading, numbers) in enumerate(plan, 1):
        name = os.path.join(deliverable, "%02d-%s.md" % (position, re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")))
        files.append(name)
        parts = ["# %s" % heading, "", "Section label `%s`. Compiled from %s." % (label, repo), ""]
        for number in numbers:
            issue = issues[number]
            text = record_format.section_text(issue["body"] or "", heading)
            if text is None:
                text = "(The body of #%d has no '## %s' section, although the issue carries %s.)" % (number, heading, label)
            parts += ["## %s (#%d)" % (issue["title"], number), "", issue["url"] or "", "", text.strip(), ""]
            counts["section_texts"] += 1
        if not dry_run:
            with open(name, "w", encoding="utf-8") as handle:
                handle.write("\n".join(parts).rstrip("\n") + "\n")
        counts["sections"] += 1

    blocks = {"figure": [], "table": []}
    for row in db.execute("SELECT * FROM blocks ORDER BY issue"):
        blocks[row["kind"]].append(dict(row))
    for kind in ("figure", "table"):
        name = os.path.join(deliverable, "%ss.tsv" % kind)
        files.append(name)
        counts["%ss" % kind] = len(blocks[kind])
        if not dry_run:
            write_tsv(name, BLOCK_COLUMNS, blocks[kind])
    sources = [dict(r, issue_title=issues.get(r["issue"])["title"] if issues.get(r["issue"]) else "")
               for r in db.execute("SELECT * FROM sources ORDER BY issue, ordinal")]
    counts["sources"] = len(sources)
    files.append(os.path.join(deliverable, "sources.tsv"))
    if not dry_run:
        write_tsv(files[-1], ["issue", "issue_title", "statement", "source"], sources)

    rows = [dict(r, reconstructed="yes" if r["reconstructed"] else "no") for r in index.timeline(db)]
    counts["timeline_rows"] = len(rows)
    counts["events"] = sum(1 for r in rows if r["type"] in record_format.EVENT_TYPES)
    counts["other_comments"] = sum(1 for r in rows if r["type"] == "other")
    files += [os.path.join(history, "timeline.tsv"), os.path.join(history, "timeline.md")]
    if not dry_run:
        write_tsv(files[-2], TIMELINE_COLUMNS, rows)
        lines = ["# Timeline of %s" % repo, "",
                 "Every comment and issue event in time order. Times are as recorded: the event time from a comment's "
                 "marker or heading, else the time GitHub stored. Type \"other\" is a comment that is not a typed event.",
                 "", "| Time | Type | Issue | Title | Author | Labels |", "|---|---|---|---|---|---|"]
        for row in rows:
            lines.append("| %s | %s%s | [#%d](%s) | %s | %s | %s |" % (
                cell(row["at"]), row["type"], " (reconstructed)" if row["reconstructed"] == "yes" else "", row["issue"],
                cell(row["url"]), cell(row["title"]).replace("|", "\\|"), cell(row["author"]),
                cell(row["labels"]).replace("|", "\\|")))
        with open(files[-1], "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    manifest = {"repository": repo, "hub": hub, "ref": ref,
                "compiled_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "index_synced_at": index.get_meta(db, "synced_at"), "counts": counts,
                "files": [os.path.relpath(f, out) for f in files]}
    files.append(os.path.join(out, "MANIFEST.json"))
    if not dry_run:
        with open(files[-1], "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
    return files, counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="owner/name (default: from .gh-issues-manager.json)")
    parser.add_argument("--out", required=True, help="folder for the compiled files")
    parser.add_argument("--ref", help="git ref of the project the compilation belongs to, recorded in MANIFEST.json")
    parser.add_argument("--no-sync", action="store_true", help="use the index as it is, without reading GitHub")
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be read and written; read nothing from GitHub, write nothing")
    args = parser.parse_args(argv)

    config = ghim.load_config()
    repo = ghim.resolve_repo(args.repo, config)
    hub = config.get("hub") if config.get("repo", "").lower() == repo.lower() else None
    print(ghim.describe(config, repo))
    if args.dry_run:
        if not args.no_sync:
            print("would read (index.py sync): gh api --paginate repos/%s/issues?state=all, "
                  "repos/%s/issues/comments, the timeline of each changed issue, and their body edits" % (repo, repo))
        db = index.connect(repo, create=False)
        if db is None:
            print("would write: %s/deliverable/<NN>-<label>.md per section, figures.tsv, tables.tsv, sources.tsv, "
                  "history/timeline.tsv, history/timeline.md, MANIFEST.json (no index yet to list the sections)" % args.out)
            return 0
        files, counts = build(db, config, repo, hub, args.out, args.ref, dry_run=True)
        print("from the index synced %s:" % index.get_meta(db, "synced_at", "never"))
        for name in files:
            print("would write: %s" % name)
        return 0
    if not args.no_sync:
        summary = index.sync(repo, hub)
        print("synced: %d issues, %d comments, %d timelines changed" % (summary["issues"], summary["comments"],
                                                                         summary["timelines"]))
    db = index.connect(repo, create=False)
    if db is None:
        sys.exit("error: no index for %s; run without --no-sync" % repo)
    files, counts = build(db, config, repo, hub, args.out, args.ref)
    for name in files:
        print("wrote: %s" % name)
    print("sections %(sections)d (texts %(section_texts)d), figures %(figures)d, tables %(tables)d, sources %(sources)d, "
          "typed events %(events)d, other comments %(other_comments)d, timeline rows %(timeline_rows)d" % counts)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ghim.GhError as error:
        sys.exit("error: %s" % error)
