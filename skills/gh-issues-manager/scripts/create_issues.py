#!/usr/bin/env python3
"""Create interlinked issues and comments from drafts listed in a manifest.

Drafts refer to issues that do not exist yet as NEW-<key>. This script creates
the issues, replaces every NEW-<key> with the real number (#N in prose,
"Issue N" inside Mermaid), writes the final bodies, and reads each one back
from the API to confirm it matches the draft.

Only files named in the manifest are posted. Nothing is ever deleted. Progress
is kept in <manifest>.state.json, so a rerun continues where a failed run
stopped:
- before each creation a pending entry is written; if the run dies before the
  result is saved, the rerun first looks on GitHub for the item it may already
  have created (same author, same title or body) and adopts it;
- a body is edited only while it still is what this script wrote (the stub or
  the last text it posted); a body changed by anyone else is left alone;
- a comment is identified by its target and its draft file, not by its
  position, so the manifest can grow;
- a missing pin is retried on every run.

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
    match = re.search(r"/(?:issues|pull)/([0-9]+)", url)
    if not match:
        raise ghim.GhError("could not read an issue number from gh output: %r" % url)
    return int(match.group(1))


def comment_id_from_url(url):
    match = re.search(r"#issuecomment-([0-9]+)", url)
    if not match:
        raise ghim.GhError("could not read a comment id from gh output: %r" % url)
    return match.group(1)


def lint_all(manifest, config):
    keys = {item["key"] for item in manifest["issues"]}
    errors = 0
    for item in manifest["issues"] + manifest["comments"]:
        findings = lint_drafts.lint_text(ghim.read_text(item["_path"]), kind=item["kind"],
                                         allow_placeholders=True, known_keys=keys, config=config,
                                         labels=item.get("labels") if item in manifest["issues"] else None)
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

    findings = lint_drafts.lint_text(text, kind=item["kind"], number_checker=checker, config=config,
                                     labels=item.get("labels") if "key" in item else None)
    return lint_drafts.report(item["_path"], findings, quiet=True)


def find_created_issue(repo, title, bodies):
    """Look for an issue this account already created with this title and one of these bodies."""
    rows = json.loads(ghim.gh(["issue", "list", "--repo", repo, "--author", "@me", "--state", "all",
                               "--json", "number,title,body,url", "--limit", "200"]))
    wanted = {ghim.normalize(body) for body in bodies}
    return [row for row in rows if row.get("title") == title and ghim.normalize(row.get("body") or "") in wanted]


def find_posted_comment(repo, number, body):
    """Look for a comment by this account on the issue with exactly this body."""
    me = ghim.gh(["api", "user", "--jq", ".login"]).strip()
    rows = ghim.parse_json_stream(ghim.gh(
        ["api", "--paginate", "repos/%s/issues/%d/comments?per_page=100" % (repo, number)]))
    return [row for row in rows if (row.get("user") or {}).get("login") == me
            and ghim.normalize(row.get("body") or "") == ghim.normalize(body)]


def is_pinned(repo, number):
    return bool(json.loads(ghim.gh(["issue", "view", str(number), "--repo", repo, "--json", "isPinned"]))
                .get("isPinned"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, help="JSON manifest listing the drafts to post")
    parser.add_argument("--repo", help="owner/name (default: manifest, then .gh-issues-manager.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="lint and print every gh command; no network access, nothing written")
    args = parser.parse_args(argv)

    config = ghim.load_config()
    manifest = lint_drafts.load_manifest(args.manifest)
    manifest.setdefault("issues", [])
    manifest.setdefault("comments", [])
    repo = ghim.resolve_repo(args.repo or manifest.get("repo"), config)
    print(ghim.describe(config, repo))
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

    failures, checked = 0, {}

    # 1. Create every issue that does not exist yet.
    for item in manifest["issues"]:
        key = item["key"]
        entry = state["issues"].get(key) or {}
        if entry.get("number"):
            print("exists: NEW-%s is #%d" % (key, entry["number"]))
            continue
        draft = ghim.read_text(item["_path"])
        direct = not ghim.PLACEHOLDER_RE.search(draft)
        first_body = draft if direct else STUB
        if entry.get("pending"):
            found = find_created_issue(repo, item["title"], [STUB, draft])
            if len(found) > 1:
                print("stopped: an earlier run may have created NEW-%s, and %d issues by this account match its "
                      "title and text (%s). Put the right number into %s as issues.%s.number and rerun."
                      % (key, len(found), ", ".join("#%d" % row["number"] for row in found), state_path, key))
                return 1
            if found:
                state["issues"][key] = {"number": found[0]["number"], "url": found[0]["url"],
                                        "written": digest(found[0].get("body") or ""), "verified": None}
                save_state(state_path, state)
                print("adopted: NEW-%s is #%d, created by an earlier run that did not finish"
                      % (key, found[0]["number"]))
                continue
        state["issues"][key] = {"pending": True}
        save_state(state_path, state)
        command = ["issue", "create", "--repo", repo, "--title", item["title"], "--body-file", "-"]
        for label in item["labels"]:
            command += ["--label", label]
        url = ghim.gh(command, stdin=first_body).strip().split("\n")[-1]
        number = number_from_url(url)
        state["issues"][key] = {"number": number, "url": url, "written": digest(first_body), "verified": None}
        save_state(state_path, state)
        print("created: NEW-%s is #%d  %s" % (key, number, url))

    numbers = {key: entry["number"] for key, entry in state["issues"].items() if entry.get("number")}

    # 2. Write the final bodies, read them back, pin.
    for item in manifest["issues"]:
        key, number = item["key"], numbers[item["key"]]
        entry = state["issues"][key]
        item["_home"] = repo
        body = ghim.substitute_placeholders(ghim.read_text(item["_path"]), numbers, repo, repo)
        if entry.get("verified") == digest(body):
            print("already verified: #%d (%s)" % (number, key))
        elif final_lint(body, item, repo, numbers, config, checked):
            print("not written: #%d (%s) fails lint after substitution" % (number, key))
            failures += 1
        else:
            current = ghim.read_issue_body(repo, number)
            if digest(current) != digest(body):
                if digest(current) not in (digest(STUB), entry.get("written")):
                    print("not written: #%d (%s) was changed on GitHub since this script wrote it, so it is left "
                          "alone. To replace it on purpose, with a diff and a backup, use post_verified.py body."
                          % (number, key))
                    failures += 1
                    current = None
                else:
                    ghim.gh(["issue", "edit", str(number), "--repo", repo, "--body-file", "-"], stdin=body)
                    entry["written"] = digest(body)
                    save_state(state_path, state)
            if current is not None:
                if ghim.verify_body(body, ghim.read_issue_body(repo, number), "#%d (%s)" % (number, key)):
                    entry["written"] = entry["verified"] = digest(body)
                    save_state(state_path, state)
                else:
                    failures += 1
        if item.get("pin"):
            try:
                if not is_pinned(repo, number):
                    ghim.gh(["issue", "pin", str(number), "--repo", repo])
                pinned = is_pinned(repo, number)
            except ghim.GhError as error:
                print("pin failed: %s" % error)
                pinned = False
            entry["pinned"] = pinned
            save_state(state_path, state)
            if pinned:
                print("pinned: #%d" % number)
            else:
                print("NOT PINNED: #%d (%s); rerun to try again" % (number, key))
                failures += 1

    # 3. Post the comments. Each is known by its target and draft file.
    for index, item in enumerate(manifest["comments"]):
        target_repo = item.get("repo", repo)
        item["_home"] = repo
        target = item["issue"]
        number = target if isinstance(target, int) else numbers[ghim.PLACEHOLDER_RE.fullmatch(target).group(1)]
        label = "comment %s on %s#%d" % (item["body_file"], target_repo, number)
        body = ghim.substitute_placeholders(ghim.read_text(item["_path"]), numbers, target_repo, repo)
        slot = "%s#%d:%s" % (target_repo, number, item["body_file"])
        entry = state["comments"].get(slot) or {}
        if entry.get("url") and entry.get("verified") == digest(body):
            print("already posted: %s" % label)
            continue
        if entry.get("url") and entry.get("written") not in (None, digest(body)):
            print("not posted: %s was posted before with different text (%s). "
                  "Post a correction comment instead of changing it." % (label, entry["url"]))
            failures += 1
            continue
        if not entry.get("url"):
            if final_lint(body, item, target_repo, numbers if target_repo == repo else {}, config, checked):
                print("not posted: %s fails lint after substitution" % label)
                failures += 1
                continue
            found = find_posted_comment(target_repo, number, body) if entry.get("pending") else []
            if found:
                entry = {"url": found[0]["html_url"], "written": digest(body), "verified": None}
                print("adopted: %s, posted by an earlier run that did not finish" % label)
            else:
                state["comments"][slot] = {"pending": True}
                save_state(state_path, state)
                url = ghim.gh(["issue", "comment", str(number), "--repo", target_repo, "--body-file", "-"],
                              stdin=body).strip().split("\n")[-1]
                entry = {"url": url, "written": digest(body), "verified": None}
            state["comments"][slot] = entry
            save_state(state_path, state)
        returned = ghim.read_comment_body(target_repo, comment_id_from_url(entry["url"]))
        if ghim.verify_body(body, returned, label):
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
    print("note: commands are listed issue by issue. The real run creates all issues first, then writes "
          "the bodies, then posts the comments.")
    known = {key: entry["number"] for key, entry in state.get("issues", {}).items() if entry.get("number")}
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
            "%s, %d characters" % (item["body_file"], len(ghim.read_text(item["_path"])))))
        print("would read back: gh api repos/%s/issues/comments/<id> and compare with %s"
              % (target_repo, item["body_file"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ghim.GhError as error:
        sys.exit("error: %s\nrerun the same command to continue; finished items are skipped" % error)
