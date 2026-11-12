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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghim  # noqa: E402

PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "profiles")
TOPIC_COLOR = "0e8a16"


def load_profile(name):
    path = name if os.path.isfile(name) else os.path.join(PROFILE_DIR, name + ".json")
    if not os.path.isfile(path):
        available = sorted(f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json"))
        sys.exit("error: no profile %r. Available: %s" % (name, ", ".join(available)))
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def wanted_labels(profiles, topics):
    labels, seen = [], set()
    names = ["core"] + [p for p in profiles if p != "core"]
    for name in names:
        for label in load_profile(name)["labels"]:
            if label["name"] not in seen:
                seen.add(label["name"])
                labels.append(label)
    for topic in topics:
        name = topic if topic.startswith("topic:") else "topic:" + topic
        if name not in seen:
            seen.add(name)
            labels.append({"name": name, "color": TOPIC_COLOR, "description": "Topic: " + name[6:]})
    for label in labels:
        if len(label["name"]) > 50:
            sys.exit("error: label name over 50 characters: %s" % label["name"])
        if len(label.get("description", "")) > 100:
            sys.exit("error: description over 100 characters for label %s" % label["name"])
    return labels


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="owner/name (default: from .gh-issues-manager.json)")
    parser.add_argument("--profile", help="comma-separated profiles: software, research, prototyping, manuscript")
    parser.add_argument("--topic", action="append", default=[], help="topic label to add (repeatable)")
    parser.add_argument("--update", action="store_true", help="also change color and description of existing labels")
    parser.add_argument("--dry-run", action="store_true", help="print the gh commands without running any")
    parser.add_argument("--existing", help="JSON file with existing labels, for an offline dry run")
    args = parser.parse_args(argv)

    config = ghim.load_config()
    repo = ghim.resolve_repo(args.repo, config)
    profiles = [p.strip() for p in (args.profile or ",".join(config.get("profiles", []))).split(",") if p.strip()]
    topics = args.topic or config.get("topics", [])
    labels = wanted_labels(profiles, topics)

    if args.existing:
        existing_list = json.loads(ghim.read_text(args.existing))
    elif args.dry_run:
        existing_list = None
    else:
        existing_list = json.loads(ghim.gh(
            ["label", "list", "--repo", repo, "--json", "name,color,description", "--limit", "1000"]))
    existing = None if existing_list is None else {l["name"].lower(): l for l in existing_list}

    print("repository: %s   profiles: core%s   labels wanted: %d"
          % (repo, "".join(", " + p for p in profiles if p != "core"), len(labels)))
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
            print("would run: " + ghim.show_command(command))
        else:
            ghim.gh(command)
            print("ran: " + ghim.show_command(command))

    verb = "would create" if args.dry_run else "created"
    print("%s %d, %s %d, already correct %d, different and left alone %d"
          % (verb, created, "would update" if args.dry_run else "updated", updated, same, differ))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ghim.GhError as error:
        sys.exit("error: %s" % error)
