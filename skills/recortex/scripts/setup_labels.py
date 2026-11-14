#!/usr/bin/env python3
"""Create the labels a project needs, from one or more profiles. Idempotent.

Labels that already exist are left alone. A label whose color or description
differs from the profile is reported, and changed only with --update. No label
is ever deleted.

Examples:
  setup_labels.py --repo owner/name --profile research --dry-run
  setup_labels.py --repo owner/name --profile software,manuscript --topic parser --topic io
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recortex  # noqa: E402

TOPIC_COLOR = "0e8a16"


def load_profile(name, shipped_only=True):
    try:
        return recortex.load_profile(name, shipped_only=shipped_only)
    except ValueError as error:
        sys.exit("error: %s" % error)


def wanted_labels(profiles, topics, shipped_only=True):
    """Labels of core and the given profiles. A profile entry with sections chosen at setup brings its own section
    labels in place of the profile's default ones, plus the profile's other labels (its issue types). Profiles named
    in a project's setup are shipped profiles only; a profile file by path is read only when the user names it with
    --profile (shipped_only=False)."""
    labels, seen = [], set()
    entries = ["core"] + [p for p in profiles if p != "core"]
    for entry in entries:
        if isinstance(entry, dict):
            parsed = recortex.custom_sections(entry)
            if parsed is None:
                sys.exit("error: a profile entry with sections is not valid: %s" % json.dumps(entry)[:200])
            profile = load_profile(parsed[0])
            color = next((l["color"] for l in profile["labels"] if l.get("heading")), "1d76db")
            what = re.sub(r"^Issue body is (.*) for: .*$", r"\1", next(
                (l["description"] for l in profile["labels"] if l.get("heading")), "Issue body is deliverable text for: x"))
            own = [{"name": label, "color": color, "description": ("Issue body is %s for: %s" % (what, heading.lower()))[:100]}
                   for label, heading in parsed[1]]
            own += [l for l in profile["labels"] if not l.get("heading")]
        else:
            own = load_profile(entry, shipped_only=shipped_only)["labels"]
        for label in own:
            if label["name"] not in seen:
                seen.add(label["name"])
                labels.append({k: label[k] for k in ("name", "color", "description") if k in label})
    for topic in topics:
        name = topic if topic.startswith("topic:") else "topic:" + topic
        if name not in seen:
            seen.add(name)
            labels.append({"name": name, "color": TOPIC_COLOR, "description": "Topic: " + name[6:]})
    for label in labels:
        if "," in label["name"]:
            sys.exit("error: label name contains a comma, which gh reads as a separator: %s" % label["name"])
        if len(label["name"]) > 50:
            sys.exit("error: label name over 50 characters: %s" % label["name"])
        if len(label.get("description", "")) > 100:
            sys.exit("error: description over 100 characters for label %s" % label["name"])
    return labels


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="owner/name (default: from .recortex.json)")
    parser.add_argument("--profile", help="comma-separated profiles: software, research, prototyping, manuscript")
    parser.add_argument("--topic", action="append", default=[], help="topic label to add (repeatable)")
    parser.add_argument("--update", action="store_true", help="also change color and description of existing labels")
    parser.add_argument("--dry-run", action="store_true", help="print the gh commands without running any")
    parser.add_argument("--existing", help="JSON file with existing labels, for an offline dry run")
    args = parser.parse_args(argv)

    config = recortex.load_config()
    repo = recortex.resolve_repo(args.repo, config)
    profiles = [p.strip() for p in args.profile.split(",") if p.strip()] if args.profile else \
        list(config.get("profiles") or [])
    topics = args.topic or config.get("topics", [])
    labels = wanted_labels(profiles, topics, shipped_only=not args.profile)

    if args.existing:
        existing_list = json.loads(recortex.read_text(args.existing))
    elif args.dry_run:
        existing_list = None
    else:
        existing_list = json.loads(recortex.gh(
            ["label", "list", "--repo", repo, "--json", "name,color,description", "--limit", "1000"]))
    existing = None if existing_list is None else {l["name"].lower(): l for l in existing_list}

    print(recortex.describe(config, repo))
    print("repository: %s   profiles: core%s   labels wanted: %d"
          % (repo, "".join(", " + p for p in recortex.profile_names(profiles) if p != "core"), len(labels)))
    if existing is None:
        print("dry run without --existing: the repository was not read, so every label is shown as a creation")

    created = updated = same = differ = 0
    for label in labels:
        name, color, description = label["name"], label["color"].lower(), label.get("description", "")
        current = existing.get(name.lower()) if existing is not None else None
        if current is None:
            command = ["label", "create", name, "--repo", repo, "--color", color, "--description", description]
            created += 1
        elif current.get("color", "").lower() == color and (current.get("description") or "") == description:
            same += 1
            continue
        elif args.update:
            command = ["label", "edit", current["name"], "--repo", repo, "--color", color, "--description", description]
            updated += 1
        else:
            differ += 1
            print("differs, left alone: %s (use --update to change color or description)" % name)
            continue
        if args.dry_run:
            print("would run: " + recortex.show_command(command))
        else:
            recortex.gh(command)
            print("ran: " + recortex.show_command(command))

    verb = "would create" if args.dry_run else "created"
    print("%s %d, %s %d, already correct %d, different and left alone %d"
          % (verb, created, "would update" if args.dry_run else "updated", updated, same, differ))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except recortex.GhError as error:
        sys.exit("error: %s" % error)
