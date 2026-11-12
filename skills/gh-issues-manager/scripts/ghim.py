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


def project_root():
    """The one folder a configuration file is read from.

    CLAUDE_PROJECT_DIR when set (Claude Code sets it for hooks, not for
    commands an agent runs), else the top of the git checkout that contains the
    current folder, else the current folder. Parent folders are never searched
    for a configuration file: a file planted above the project must not be
    able to configure it.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return os.path.abspath(env)
    try:
        proc = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=5)
        if proc.returncode == 0 and proc.stdout.strip():
            return os.path.abspath(proc.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return os.getcwd()


def find_config():
    """Path of the project's configuration file, or None.

    GHIM_CONFIG, set by the user, names a file explicitly. Otherwise only
    <project root>/.gh-issues-manager.json is considered.
    """
    env = os.environ.get("GHIM_CONFIG")
    if env:
        return env if os.path.isfile(env) else None
    candidate = os.path.join(project_root(), CONFIG_NAME)
    return candidate if os.path.isfile(candidate) else None


def load_config():
    path = find_config()
    if not path:
        return {}
    with open(path, encoding="utf-8") as handle:
        cfg = json.load(handle)
    if not isinstance(cfg, dict):
        raise ValueError("%s must hold a JSON object" % path)
    cfg["_path"] = path
    return cfg


def trusted_file():
    env = os.environ.get("GHIM_TRUSTED_FILE")
    if env:
        return env
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "gh-issues-manager", "trusted-repos")


def trusted_repos():
    """Repositories the user has trusted, as {"owner/name": {extra allowed logins}}.

    Read from the user-level file (one "owner/name [login ...]" per line, # for
    comments) and from GHIM_TRUSTED_REPOS (comma-separated owner/name). Both
    belong to the user; nothing inside a project can add to this list.
    Keys and logins are lowercase.
    """
    trusted = {}
    try:
        with open(trusted_file(), encoding="utf-8") as handle:
            for line in handle:
                parts = line.split("#", 1)[0].split()
                if parts and re.fullmatch(r"[\w.-]+/[\w.-]+", parts[0]):
                    trusted.setdefault(parts[0].lower(), set()).update(p.lower() for p in parts[1:])
    except OSError:
        pass
    for name in os.environ.get("GHIM_TRUSTED_REPOS", "").split(","):
        name = name.strip().lower()
        if re.fullmatch(r"[\w.-]+/[\w.-]+", name):
            trusted.setdefault(name, set())
    return trusted


def allowed_users(repo, trusted=None):
    """Logins whose hub text may be shown.

    Empty unless the user trusted the repository. For a trusted repository: its
    owner plus the logins listed for it in the user-level trusted file.
    """
    trusted = trusted_repos() if trusted is None else trusted
    if repo.lower() not in trusted:
        return set()
    return {repo.split("/")[0].lower()} | trusted[repo.lower()]


EDITS_CHECKED = 100

HUB_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      body
      author { login }
      editor { login }
      lastEditedAt
      head: userContentEdits(first: 100) { totalCount nodes { editedAt editor { login } } }
      tail: userContentEdits(last: 100) { nodes { editedAt editor { login } } }
    }
  }
}"""


def read_hub_with_editors(repo, number, timeout=60):
    """One call that returns the hub body together with who wrote and edited it.

    Returns (body, author, editors, problem).
    - author: login, or None for a deleted account.
    - editors: logins of the account named as the issue's current editor and of
      the newest EDITS_CHECKED body edits. None stands for an unknown account.
      Both ends of the edit list are fetched and the newest entries are chosen
      by their editedAt time, so the result does not depend on the order in
      which the API lists edits.
    - problem: None, or the reason the edit history could not be trusted
      (the issue was edited but no edit, or not the newest one, was returned).
    """
    owner, name = repo.split("/")
    raw = gh(["api", "graphql", "-f", "query=" + HUB_QUERY, "-f", "owner=" + owner,
              "-f", "name=" + name, "-F", "number=%d" % number], timeout=timeout)
    issue = (((json.loads(raw).get("data") or {}).get("repository") or {}).get("issue"))
    if not issue:
        raise GhError("hub %s#%d not found" % (repo, number))

    def login(node):
        return (node or {}).get("login")

    edits = {}
    for end in ("head", "tail"):
        for node in ((issue.get(end) or {}).get("nodes") or []):
            if node and node.get("editedAt"):
                edits.setdefault((node["editedAt"], login(node.get("editor"))), None)
    newest = sorted(edits, reverse=True)[:EDITS_CHECKED]
    editors = {who for _, who in newest}
    last_edited = issue.get("lastEditedAt")
    problem = None
    if last_edited:
        editors.add(login(issue.get("editor")))
        if not newest:
            problem = "the issue was edited but its edit history came back empty"
        elif newest[0][0] < last_edited:
            problem = "the newest edit was not in the returned edit history"
    return issue.get("body") or "", login(issue.get("author")), editors, problem


def describe(config, repo):
    """The line every writing or dry-running script prints first."""
    return "config: %s  repo: %s" % (config.get("_path") or "none (repository given on the command line or in the manifest)", repo)


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
    is "Issue N", because # breaks Mermaid on GitHub. Inline code spans and
    fenced blocks other than Mermaid are left as they are.
    """
    out, region, fence = [], "prose", None

    def repl(match):
        key = match.group(1)
        if key not in numbers:
            return match.group(0)
        if region == "mermaid":
            return "Issue %d" % numbers[key]
        if target_repo != home_repo:
            return "%s#%d" % (home_repo, numbers[key])
        return "#%d" % numbers[key]

    for line in text.split("\n"):
        stripped = line.strip()
        opening = re.match(r"^(```+|~~~+)", stripped)
        if fence is None and opening:
            fence = opening.group(1)
            region = "mermaid" if stripped[len(fence):].strip().lower() == "mermaid" else "code"
            out.append(line)
        elif fence is not None and stripped.startswith(fence) and stripped.strip(fence[0]) == "":
            fence, region = None, "prose"
            out.append(line)
        elif region == "code":
            out.append(line)
        elif region == "mermaid":
            out.append(PLACEHOLDER_RE.sub(repl, line))
        else:
            parts = re.split(r"(`[^`\n]*`)", line)
            out.append("".join(part if part.startswith("`") and part.endswith("`") and len(part) > 1
                               else PLACEHOLDER_RE.sub(repl, part) for part in parts))
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
