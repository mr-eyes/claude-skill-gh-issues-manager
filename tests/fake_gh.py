#!/usr/bin/env python3
"""A local stand-in for the gh CLI, used only by the tests.

It keeps a small repository in a JSON file (FAKE_GH_STATE) and answers the
subset of gh commands the scripts use, in the formats the real gh prints.
Fault switches:
  FAKE_GH_FAIL_ON="issue edit"   exit 1 for commands starting with these words
  FAKE_GH_CORRUPT=1              store bodies with one character changed
  FAKE_GH_SLEEP=5                sleep before answering
"""

import json
import os
import re
import sys
import time


def load():
    with open(os.environ["FAKE_GH_STATE"], encoding="utf-8") as handle:
        return json.load(handle)


def save(state):
    with open(os.environ["FAKE_GH_STATE"], "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=1)


def option(args, name, default=None, many=False):
    values = [args[i + 1] for i, a in enumerate(args[:-1]) if a == name]
    if many:
        return values
    return values[-1] if values else default


def body_from(args):
    path = option(args, "--body-file")
    text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    if os.environ.get("FAKE_GH_CORRUPT"):
        text = text.replace("e", "E", 1)
    return text.replace("\n", "\r\n")  # bodies can come back with CRLF line endings


def fail(message, code=1):
    sys.stderr.write(message + "\n")
    sys.exit(code)


def api_issue(state, repo, number):
    issue = state["issues"].get(str(number))
    if issue is None:
        sys.stdout.write('{"message":"Not Found","status":"404"}')
        fail("gh: Not Found (HTTP 404)")
    kind = "pull" if issue.get("pull_request") else "issues"
    out = {
        "number": int(number), "title": issue["title"], "state": issue.get("state", "open"),
        "body": issue["body"], "labels": [{"name": n} for n in issue.get("labels", [])],
        "user": {"login": issue.get("user", "octo-dev")},
        "created_at": issue.get("created_at", "2026-01-05T17:00:00Z"),
        "updated_at": issue.get("updated_at", "2026-01-06T18:30:00Z"),
        "html_url": "https://github.com/%s/%s/%s" % (repo, kind, number),
    }
    if issue.get("pull_request"):
        out["pull_request"] = {"url": "https://api.github.com/repos/%s/pulls/%s" % (repo, number)}
    return out


def api_comment(state, repo, cid):
    comment = state["comments"][str(cid)]
    return {
        "id": int(cid), "body": comment["body"], "user": {"login": comment.get("user", "octo-dev")},
        "created_at": comment.get("created_at", "2026-01-07T09:15:00Z"),
        "issue_url": "https://api.github.com/repos/%s/issues/%d" % (repo, comment["issue"]),
        "html_url": "https://github.com/%s/issues/%d#issuecomment-%s" % (repo, comment["issue"], cid),
    }


def main():
    args = sys.argv[1:]
    if os.environ.get("FAKE_GH_SLEEP"):
        time.sleep(float(os.environ["FAKE_GH_SLEEP"]))
    state = load()
    state.setdefault("log", []).append(args)
    save(state)
    words = " ".join(args[:2])
    fail_on = os.environ.get("FAKE_GH_FAIL_ON")
    if fail_on and words.startswith(fail_on):
        fail("gh: simulated failure (HTTP 502)")
    repo = option(args, "--repo", "octo/demo")

    if words == "label list":
        print(json.dumps(state["labels"]))
    elif words == "label create":
        state["labels"].append({"name": args[2], "color": option(args, "--color", ""),
                                "description": option(args, "--description", "")})
    elif words == "label edit":
        for label in state["labels"]:
            if label["name"] == args[2]:
                label["color"] = option(args, "--color", label["color"])
                label["description"] = option(args, "--description", label["description"])
    elif words == "issue create":
        number = state["next_issue"]
        state["next_issue"] += 1
        state["issues"][str(number)] = {"title": option(args, "--title"), "body": body_from(args),
                                        "labels": option(args, "--label", many=True)}
        print("https://github.com/%s/issues/%d" % (repo, number))
    elif words == "issue edit":
        if args[2] not in state["issues"]:
            fail("gh: Not Found (HTTP 404)")
        state["issues"][args[2]]["body"] = body_from(args)
        print("https://github.com/%s/issues/%s" % (repo, args[2]))
    elif words == "issue comment":
        if args[2] not in state["issues"]:
            fail("gh: Not Found (HTTP 404)")
        cid = state["next_comment"]
        state["next_comment"] += 1
        state["comments"][str(cid)] = {"issue": int(args[2]), "body": body_from(args)}
        print("https://github.com/%s/issues/%s#issuecomment-%d" % (repo, args[2], cid))
    elif words == "issue pin":
        state["issues"][args[2]]["pinned"] = True
    elif words == "issue list":
        label = option(args, "--label")
        rows = [{"number": int(n), "title": i["title"], "updatedAt": i.get("updated_at", "2026-01-06T18:30:00Z"),
                 "author": {"login": i.get("user", "octo-dev")}}
                for n, i in sorted(state["issues"].items(), key=lambda kv: int(kv[0]))
                if label in i.get("labels", []) and i.get("state", "open") == "open"]
        print(json.dumps(rows))
    elif args[:2] == ["api", "graphql"]:
        fields = dict(a.split("=", 1) for a in option(args, "-f", many=True) + option(args, "-F", many=True))
        issue = state["issues"].get(fields["number"])
        if issue is None:
            print(json.dumps({"data": {"repository": {"issue": None}}}))
        else:
            person = lambda name: {"login": name} if name else None
            editors = issue.get("editors", [])
            print(json.dumps({"data": {"repository": {"issue": {
                "body": issue["body"],
                "author": person(issue.get("user", "octo-dev")),
                "lastEditedBy": person(editors[-1]) if editors else None,
                "userContentEdits": {"totalCount": issue.get("edit_count", len(editors)),
                                     "nodes": [{"editor": person(e)} for e in editors]},
            }}}}))
    elif args[0] == "api":
        path = [a for a in args[1:] if a.startswith("repos/")][0]
        jq = option(args, "--jq")
        match = re.fullmatch(r"repos/([^/]+/[^/]+)/issues/comments/(\d+)", path)
        if match:
            out = api_comment(state, match.group(1), match.group(2))
        elif re.fullmatch(r"repos/([^/]+/[^/]+)/issues/(\d+)", path):
            match = re.fullmatch(r"repos/([^/]+/[^/]+)/issues/(\d+)", path)
            out = api_issue(state, match.group(1), match.group(2))
            if jq == ".number":
                print(out["number"])
                save(state)
                return
        elif re.fullmatch(r"repos/([^/]+/[^/]+)/issues/comments\?.*", path):
            api_repo = path.split("/issues")[0][6:]
            rows = [api_comment(state, api_repo, c) for c in sorted(state["comments"], key=int)]
            # the real gh prints one JSON array per page, back to back
            sys.stdout.write(json.dumps(rows[:1]) + json.dumps(rows[1:]))
            save(state)
            return
        elif re.fullmatch(r"repos/([^/]+/[^/]+)/issues\?.*", path):
            api_repo = path.split("/issues")[0][6:]
            rows = [api_issue(state, api_repo, n) for n in sorted(state["issues"], key=int)]
            sys.stdout.write(json.dumps(rows[:2]) + json.dumps(rows[2:]))
            save(state)
            return
        else:
            fail("fake gh: unsupported api path %s" % path, 3)
        print(json.dumps(out))
    else:
        fail("fake gh: unsupported command %s" % words, 3)
    save(state)


if __name__ == "__main__":
    main()
