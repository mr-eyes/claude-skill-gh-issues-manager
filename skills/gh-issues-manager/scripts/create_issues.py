#!/usr/bin/env python3
"""Create interlinked issues and comments from drafts listed in a manifest.

Drafts refer to issues that do not exist yet as NEW-<key>. This script creates
the issues, replaces every NEW-<key> with the real number (#N in prose,
"Issue N" inside Mermaid), writes the final bodies, and reads each one back
from the API to confirm it matches the draft.

Only files named in the manifest are posted. Nothing is ever deleted. Progress
is kept in <manifest>.state.json, so a rerun continues where a failed run
stopped and never creates an issue twice.

Manifest (JSON):
  {"repo": "owner/name",
   "issues":   [{"key": "hub", "kind": "hub", "title": "...", "labels": ["hub"],
                 "body_file": "hub.md", "pin": true}],
   "comments": [{"issue": "NEW-hub", "kind": "checkpoint", "body_file": "c1.md"},
                {"issue": 7, "repo": "owner/old-tracker", "kind": "pointer", "body_file": "p7.md"}]}

Examples:
  create_issues.py --manifest drafts/manifest.json --dry-run
  create_issues.py --manifest drafts/manifest.json
"""

import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghim  # noqa: E402
import lint_drafts  # noqa: E402

STUB = "This issue is being created. Its full text follows within minutes."


def digest(text):
    return hashlib.sha256(ghim.normalize(text).encode("utf-8")).hexdigest()[:16]


def save_state(path, state):
    with open(path + ".part", "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(path + ".part", path)


def number_from_url(url):
    match = re.search(r"/(?:issues|pull)/(\d+)", url)
    if not match:
        raise ghim.GhError("could not read an issue number from gh output: %r" % url)
    return int(match.group(1))


def comment_id_from_url(url):
    match = re.search(r"#issuecomment-(\d+)", url)
    if not match:
        raise ghim.GhError("could not read a comment id from gh output: %r" % url)
    return match.group(1)


def lint_all(manifest, config):
    keys = {item["key"] for item in manifest["issues"]}
    errors = 0
    for item in manifest["issues"] + manifest["comments"]:
        findings = lint_drafts.lint_text(ghim.read_text(item["_path"]), kind=item["kind"],
                                         allow_placeholders=True, known_keys=keys, config=config)
        findings = [f for f in findings if not (f.code == "bare-ref" and f.level == "warning")]
        errors += lint_drafts.report(item["_path"], findings, quiet=True)
    return errors


def final_lint(text, item, repo, numbers, config, checked):
    def checker(number):
        if number in numbers.values() and repo == item.get("_home"):
            return True
        if (repo, number) not in checked:
            checked[(repo, number)] = ghim.number_exists(repo, number)
        return checked[(repo, number)]

    findings = lint_drafts.lint_text(text, kind=item["kind"], number_checker=checker, config=config)
    return lint_drafts.report(item["_path"], findings, quiet=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, help="JSON manifest listing the drafts to post")
    parser.add_argument("--repo", help="owner/name (default: manifest, then .gh-issues-manager.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="lint and print every gh command; no network access, nothing written")
    args = parser.parse_args(argv)

    config = ghim.load_config(os.path.dirname(os.path.abspath(args.manifest)))
    manifest = lint_drafts.load_manifest(args.manifest)
    manifest.setdefault("issues", [])
    manifest.setdefault("comments", [])
    repo = ghim.resolve_repo(args.repo or manifest.get("repo"), config)
    state_path = args.manifest + ".state.json"
    state = {"repo": repo, "issues": {}, "comments": {}}
    if os.path.isfile(state_path):
        state = json.loads(ghim.read_text(state_path))
        if state.get("repo") != repo:
            sys.exit("error: %s belongs to %s, not %s" % (state_path, state.get("repo"), repo))

    print("manifest: %s   repository: %s   issues: %d   comments: %d"
          % (args.manifest, repo, len(manifest["issues"]), len(manifest["comments"])))
    if lint_all(manifest, config):
        print("nothing posted: fix the lint errors above")
        return 1
    print("lint: all %d drafts pass" % (len(manifest["issues"]) + len(manifest["comments"])))

    if args.dry_run:
        return dry_run(manifest, repo, state)

    wanted = sorted({label for item in manifest["issues"] for label in item["labels"]})
    have = {l["name"].lower() for l in json.loads(ghim.gh(
        ["label", "list", "--repo", repo, "--json", "name", "--limit", "1000"]))}
    missing = [label for label in wanted if label.lower() not in have]
    if missing:
        print("nothing posted: these labels do not exist in %s: %s" % (repo, ", ".join(missing)))
        print("run setup_labels.py first")
        return 1

    numbers = {key: entry["number"] for key, entry in state["issues"].items()}
    failures, checked = 0, {}

    # 1. Create every issue that does not exist yet.
    for item in manifest["issues"]:
        key = item["key"]
        if key in numbers:
            print("exists: NEW-%s is #%d" % (key, numbers[key]))
            continue
        draft = ghim.read_text(item["_path"])
        direct = not ghim.PLACEHOLDER_RE.search(draft)
        command = ["issue", "create", "--repo", repo, "--title", item["title"], "--body-file", "-"]
        for label in item["labels"]:
            command += ["--label", label]
        url = ghim.gh(command, stdin=draft if direct else STUB).strip().split("\n")[-1]
        numbers[key] = number_from_url(url)
        state["issues"][key] = {"number": numbers[key], "url": url, "verified": None}
        save_state(state_path, state)
        print("created: NEW-%s is #%d  %s" % (key, numbers[key], url))

    # 2. Write the final bodies and read them back.
    for item in manifest["issues"]:
        key, number = item["key"], numbers[item["key"]]
        item["_home"] = repo
        body = ghim.substitute_placeholders(ghim.read_text(item["_path"]), numbers, repo, repo)
        if state["issues"][key].get("verified") == digest(body):
            print("already verified: #%d (%s)" % (number, key))
            continue
        if final_lint(body, item, repo, numbers, config, checked):
            print("not written: #%d (%s) fails lint after substitution" % (number, key))
            failures += 1
            continue
        if ghim.normalize(ghim.read_issue_body(repo, number)) != ghim.normalize(body):
            ghim.gh(["issue", "edit", str(number), "--repo", repo, "--body-file", "-"], stdin=body)
        if ghim.verify_body(body, ghim.read_issue_body(repo, number), "#%d (%s)" % (number, key)):
            state["issues"][key]["verified"] = digest(body)
            save_state(state_path, state)
        else:
            failures += 1
        if item.get("pin") and not state["issues"][key].get("pinned"):
            ghim.gh(["issue", "pin", str(number), "--repo", repo])
            state["issues"][key]["pinned"] = True
            save_state(state_path, state)
            print("pinned: #%d" % number)

    # 3. Post the comments, in manifest order.
    for index, item in enumerate(manifest["comments"]):
        target_repo = item.get("repo", repo)
        item["_home"] = repo
        target = item["issue"]
        number = target if isinstance(target, int) else numbers[ghim.PLACEHOLDER_RE.fullmatch(target).group(1)]
        body = ghim.substitute_placeholders(ghim.read_text(item["_path"]), numbers, target_repo, repo)
        slot = "%d:%s" % (index, item["body_file"])
        done = state["comments"].get(slot)
        if done and done.get("verified") == digest(body):
            print("already posted: comment %d on %s#%d" % (index + 1, target_repo, number))
            continue
        if done:
            print("not posted: comment %d was posted before with different text (%s). "
                  "Post a correction comment instead of changing it." % (index + 1, done.get("url")))
            failures += 1
            continue
        if final_lint(body, item, target_repo, numbers if target_repo == repo else {}, config, checked):
            print("not posted: comment %d fails lint after substitution" % (index + 1))
            failures += 1
            continue
        url = ghim.gh(["issue", "comment", str(number), "--repo", target_repo, "--body-file", "-"],
                      stdin=body).strip().split("\n")[-1]
        entry = {"url": url, "verified": None}
        state["comments"][slot] = entry
        save_state(state_path, state)
        returned = ghim.read_comment_body(target_repo, comment_id_from_url(url))
        if ghim.verify_body(body, returned, "comment %d on %s#%d" % (index + 1, target_repo, number)):
            entry["verified"] = digest(body)
            save_state(state_path, state)
        else:
            failures += 1

    print("")
    print("key -> issue")
    for item in manifest["issues"]:
        print("  NEW-%s -> #%d  %s" % (item["key"], numbers[item["key"]], state["issues"][item["key"]]["url"]))
    print("state file: %s" % state_path)
    if failures:
        print("%d item(s) failed; fix and rerun the same command" % failures)
        return 1
    print("all items posted and verified")
    return 0


def dry_run(manifest, repo, state):
    print("dry run: no network access, nothing written")
    known = {key: entry["number"] for key, entry in state.get("issues", {}).items()}
    for item in manifest["issues"]:
        key = item["key"]
        draft = ghim.read_text(item["_path"])
        refs = sorted(set(ghim.PLACEHOLDER_RE.findall(draft)))
        if key in known:
            print("exists: NEW-%s is #%d (from the state file)" % (key, known[key]))
        else:
            command = ["issue", "create", "--repo", repo, "--title", item["title"], "--body-file", "-"]
            for label in item["labels"]:
                command += ["--label", label]
            note = "body: %s" % ("a one-line stub, replaced in the next step" if refs
                                 else "%s, %d characters" % (item["body_file"], len(draft)))
            print("would run: " + ghim.show_command(command, note))
        if refs or key in known:
            print("would run: " + ghim.show_command(
                ["issue", "edit", "<number of NEW-%s>" % key, "--repo", repo, "--body-file", "-"],
                "%s, %d characters, with %s replaced by real numbers"
                % (item["body_file"], len(draft), ", ".join("NEW-" + r for r in refs) or "no placeholders")))
        print("would read back: gh api repos/%s/issues/<number of NEW-%s> and compare with %s"
              % (repo, key, item["body_file"]))
        if item.get("pin"):
            print("would run: " + ghim.show_command(["issue", "pin", "<number of NEW-%s>" % key, "--repo", repo]))
    for index, item in enumerate(manifest["comments"]):
        target = item["issue"]
        shown = str(target) if isinstance(target, int) else "<number of %s>" % target
        target_repo = item.get("repo", repo)
        print("would run: " + ghim.show_command(
            ["issue", "comment", shown, "--repo", target_repo, "--body-file", "-"],
            "comment %d: %s, %d characters" % (index + 1, item["body_file"], len(ghim.read_text(item["_path"])))))
        print("would read back: gh api repos/%s/issues/comments/<id> and compare with %s"
              % (target_repo, item["body_file"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ghim.GhError as error:
        sys.exit("error: %s\nrerun the same command to continue; finished items are skipped" % error)
