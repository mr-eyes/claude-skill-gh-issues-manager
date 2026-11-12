"""Shared helpers for the gh-issues-manager scripts.

Python 3 standard library only. All GitHub access goes through the gh CLI.
Set GHIM_GH to replace the gh command (the tests point it at a local fake).
"""

import json
import os
import re
import shlex
import subprocess
import sys

CONFIG_NAME = ".gh-issues-manager.json"
BODY_LIMIT = 65536
RESUME_START = "<!-- resume:start -->"
RESUME_END = "<!-- resume:end -->"
RESUME_LIMIT = 4000
PLACEHOLDER_RE = re.compile(r"\bNEW-([a-z0-9]+(?:-[a-z0-9]+)*)")


class GhError(RuntimeError):
    pass


def gh_command():
    return shlex.split(os.environ.get("GHIM_GH", "gh"))


def gh(args, stdin=None, timeout=60):
    """Run gh with the given arguments and return stdout. Raise GhError on failure."""
    cmd = gh_command() + list(args)
    try:
        proc = subprocess.run(
            cmd, input=stdin, capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        raise GhError("gh CLI not found (looked for: %s)" % cmd[0])
    except subprocess.TimeoutExpired:
        raise GhError("gh timed out after %ss: %s" % (timeout, " ".join(args[:3])))
    if proc.returncode != 0:
        raise GhError(
            "gh %s failed (exit %d): %s"
            % (" ".join(args[:3]), proc.returncode, proc.stderr.strip())
        )
    return proc.stdout


def show_command(args, note=""):
    """Format a gh command for dry-run output."""
    text = "gh " + " ".join(shlex.quote(a) for a in args)
    return text + ("   # " + note if note else "")


def find_config(start=None):
    """Return the path of the nearest .gh-issues-manager.json at or above start."""
    env = os.environ.get("GHIM_CONFIG")
    if env:
        return env if os.path.isfile(env) else None
    here = os.path.abspath(start or os.getcwd())
    while True:
        candidate = os.path.join(here, CONFIG_NAME)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def load_config(start=None):
    path = find_config(start)
    if not path:
        return {}
    with open(path, encoding="utf-8") as handle:
        cfg = json.load(handle)
    if not isinstance(cfg, dict):
        raise ValueError("%s must hold a JSON object" % path)
    cfg["_path"] = path
    return cfg


def resolve_repo(cli_value, cfg):
    repo = cli_value or cfg.get("repo")
    if not repo or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        sys.exit(
            "error: no repository. Pass --repo owner/name or set \"repo\" in %s"
            % CONFIG_NAME
        )
    return repo


def resolve_hub(cli_value, cfg):
    hub = cli_value if cli_value is not None else cfg.get("hub")
    if not isinstance(hub, int) or hub < 1:
        sys.exit(
            "error: no hub issue number. Pass --hub N or set \"hub\" in %s"
            % CONFIG_NAME
        )
    return hub


def normalize(text):
    """Form used to compare a draft with what GitHub returns.

    Line endings become LF and trailing whitespace is dropped from every line
    and from the end of the text. Nothing else changes.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).rstrip()


def first_difference(expected, actual):
    """Describe the first place two normalized texts differ."""
    exp, act = expected.split("\n"), actual.split("\n")
    for index in range(max(len(exp), len(act))):
        left = exp[index] if index < len(exp) else "<end of text>"
        right = act[index] if index < len(act) else "<end of text>"
        if left != right:
            return "line %d\n  sent:     %r\n  returned: %r" % (index + 1, left, right)
    return "no difference"


def parse_json_stream(text):
    """Parse the output of `gh api --paginate`: one JSON value per page."""
    decoder = json.JSONDecoder()
    items, pos, length = [], 0, len(text)
    while pos < length:
        while pos < length and text[pos].isspace():
            pos += 1
        if pos >= length:
            break
        value, pos = decoder.raw_decode(text, pos)
        if isinstance(value, list):
            items.extend(value)
        else:
            items.append(value)
    return items


def read_issue_body(repo, number, timeout=60):
    data = json.loads(gh(["api", "repos/%s/issues/%d" % (repo, number)], timeout=timeout))
    return data.get("body") or ""


def read_comment_body(repo, comment_id):
    data = json.loads(gh(["api", "repos/%s/issues/comments/%s" % (repo, comment_id)]))
    return data.get("body") or ""


def number_exists(repo, number):
    """True when issue or pull request `number` exists in `repo`."""
    try:
        gh(["api", "repos/%s/issues/%d" % (repo, number), "--jq", ".number"])
        return True
    except GhError as error:
        if "404" in str(error) or "Not Found" in str(error):
            return False
        raise


def verify_body(expected, actual, what):
    """Return True when the returned text equals the sent text; print the gap otherwise."""
    left, right = normalize(expected), normalize(actual)
    if left == right:
        print("verified: %s matches the draft (%d characters)" % (what, len(left)))
        return True
    print("MISMATCH: %s differs from the draft at %s" % (what, first_difference(left, right)))
    return False


def substitute_placeholders(text, numbers, target_repo, home_repo):
    """Replace NEW-<key> with the real reference.

    In prose the reference is #N (or owner/repo#N when the text is posted to a
    repository other than the one the issues live in). Inside a Mermaid block it
    is "Issue N", because # breaks Mermaid on GitHub.
    """
    out, in_mermaid, fence = [], False, None
    for line in text.split("\n"):
        stripped = line.strip()
        if fence is None and re.match(r"^(```+|~~~+)", stripped):
            fence = re.match(r"^(```+|~~~+)", stripped).group(1)
            in_mermaid = stripped[len(fence):].strip().lower() == "mermaid"
            out.append(line)
            continue
        if fence is not None and stripped.startswith(fence) and stripped.strip(fence[0]) == "":
            fence, in_mermaid = None, False
            out.append(line)
            continue

        def repl(match):
            key = match.group(1)
            if key not in numbers:
                return match.group(0)
            if in_mermaid:
                return "Issue %d" % numbers[key]
            if target_repo != home_repo:
                return "%s#%d" % (home_repo, numbers[key])
            return "#%d" % numbers[key]

        out.append(PLACEHOLDER_RE.sub(repl, line))
    return "\n".join(out)


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def extract_resume_block(body):
    """Return the text between the resume markers, or None when they are absent or malformed."""
    if body.count(RESUME_START) != 1 or body.count(RESUME_END) != 1:
        return None
    start = body.index(RESUME_START) + len(RESUME_START)
    end = body.index(RESUME_END)
    if end < start:
        return None
    return body[start:end].strip("\n")
