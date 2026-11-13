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
RESUME_START = "<!-- ghim:resume:start -->"
RESUME_END = "<!-- ghim:resume:end -->"
RESUME_HEADING = "### Resume block: "
RESUME_LIMIT = 4000
PLACEHOLDER_RE = re.compile(r"\bNEW-([a-z0-9]+(?:-[a-z0-9]+)*)")
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "profiles")
SOURCES_HEADING = "Sources"
RECORD_HEADING = "### Record: former issue body, kept as history (not deliverable text)"


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


COMMENTS_READ = 50
EDITS_READ = 100

RESUME_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      comments(last: 50) {
        totalCount
        nodes {
          id
          url
          createdAt
          body
          author { login }
          editor { login }
          lastEditedAt
          userContentEdits(first: 100) { totalCount nodes { editedAt editor { login } } }
        }
      }
    }
  }
}"""


def read_hub_comments(repo, number, timeout=60):
    """The newest COMMENTS_READ comments of the hub, newest first by creation time.

    One GraphQL call returns each comment's text together with who wrote it and
    its edit history, so what is shown is what was checked. Each item is a dict
    with url, created, body, author, last_edited, editor, edit_total and
    edit_editors (a list of logins; None stands for an unknown account).
    """
    owner, name = repo.split("/")
    raw = gh(["api", "graphql", "-f", "query=" + RESUME_QUERY, "-f", "owner=" + owner,
              "-f", "name=" + name, "-F", "number=%d" % number], timeout=timeout)
    issue = (((json.loads(raw).get("data") or {}).get("repository") or {}).get("issue"))
    if not issue:
        raise GhError("hub %s#%d not found" % (repo, number))

    def login(node):
        return (node or {}).get("login")

    comments = []
    for node in ((issue.get("comments") or {}).get("nodes") or []):
        if not node:
            continue
        edits = node.get("userContentEdits") or {}
        comments.append({
            "url": str(node.get("url") or ""),
            "created": str(node.get("createdAt") or ""),
            "body": node.get("body") or "",
            "author": login(node.get("author")),
            "last_edited": node.get("lastEditedAt"),
            "editor": login(node.get("editor")),
            "edit_total": edits.get("totalCount") or 0,
            "edit_editors": [login(e.get("editor")) for e in (edits.get("nodes") or []) if e],
        })
    # newest first; of two comments created in the same second, the one the API lists later wins
    order = sorted(range(len(comments)), key=lambda i: (comments[i]["created"], i), reverse=True)
    return [comments[i] for i in order]


def resume_comment_problem(comment, allowed):
    """Why a comment that carries the resume markers may not be shown, or None.

    Fail closed. Resume comments are append-only: the author must be allowed
    and the comment must never have been edited, by anyone. (On GitHub an
    unedited comment has no lastEditedAt and an empty edit history; an edited
    one lists its edits plus an entry for its creation.)
    """
    if extract_resume_block(comment["body"]) is None:
        return "malformed markers"
    author = comment["author"]
    if not author or author.lower() not in allowed:
        return "written by a non-allowed account"
    if comment["last_edited"] or comment["edit_total"] > 0 or comment["edit_editors"]:
        return "edited after posting"
    return None


def pick_resume_comment(comments, allowed, any_author=False):
    """Choose the newest usable resume comment.

    Returns (comment or None, {reason: count of newer marker comments ignored}).
    `comments` must be newest first.
    """
    ignored = {}
    for comment in comments:
        if RESUME_START not in comment["body"]:
            continue
        problem = resume_comment_problem(comment, allowed)
        if any_author and problem != "malformed markers":
            problem = None
        if problem is None:
            return comment, ignored
        ignored[problem] = ignored.get(problem, 0) + 1
    return None, ignored


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


def read_issue(repo, number, timeout=60):
    """The issue's body and label names, read from the REST API."""
    data = json.loads(gh(["api", "repos/%s/issues/%d" % (repo, number)], timeout=timeout))
    return {"body": data.get("body") or "",
            "labels": [label.get("name", "") for label in data.get("labels") or []]}


def read_issue_body(repo, number, timeout=60):
    return read_issue(repo, number, timeout)["body"]


def load_profile(name):
    """A profile from profiles/<name>.json, or from a file path. Raises ValueError when there is none."""
    path = name if os.path.isfile(name) else os.path.join(PROFILE_DIR, name + ".json")
    if not os.path.isfile(path):
        available = sorted(f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json"))
        raise ValueError("no profile %r. Available: %s" % (name, ", ".join(available)))
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


LABEL_NAME = re.compile(r"[a-z0-9][a-z0-9:._-]{0,49}")
HEADING_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ,.'()-]{0,59}")
PROFILE_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def shipped_profiles(names):
    """Only the names of profiles shipped in profiles/; hooks never load a profile from a path a project names."""
    out = []
    for name in names or []:
        if isinstance(name, str) and PROFILE_NAME.fullmatch(name) and \
                os.path.isfile(os.path.join(PROFILE_DIR, name + ".json")):
            out.append(name)
    return out


def section_labels(profiles):
    """The deliverable-section labels of the given profiles, as a list of (label, heading).

    A section label is a profile label with a "heading": the level-2 heading
    that a topic body uses for the text of that section. Labels and headings
    that do not fit a plain pattern (letters, digits, a few punctuation marks,
    a length limit) are left out, so a custom profile cannot carry other text.
    """
    out = []
    for name in profiles:
        for label in load_profile(name).get("labels", []):
            heading, label_name = label.get("heading"), label.get("name")
            if isinstance(heading, str) and isinstance(label_name, str) and \
                    HEADING_TEXT.fullmatch(heading) and LABEL_NAME.fullmatch(label_name):
                out.append((label_name, heading))
    return out


def body_sections(text):
    """The level-2 headings of a body outside fenced blocks, as a list of (line number, heading text)."""
    found, fence = [], None
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        stripped = line.strip()
        opening = re.match(r"^(```+|~~~+)", stripped)
        if fence is None and opening:
            fence = opening.group(1)
            continue
        if fence is not None:
            if stripped.startswith(fence) and stripped.strip(fence[0]) == "":
                fence = None
            continue
        match = re.match(r"^## +(.*?)\s*#*\s*$", line)
        if match:
            found.append((number, match.group(1).strip()))
    return found


def labels_from_headings(text, profiles, intended=None):
    """The section labels a body's headings call for.

    Returns (labels, problems). When the profiles define section labels, every
    level-2 heading other than "Sources" must be the heading of one of them. When several profiles
    use the same heading, the labels in `intended` choose between them;
    without a choice the heading is reported as ambiguous.
    """
    by_heading = {}
    for label, heading in section_labels(profiles):
        by_heading.setdefault(heading.lower(), []).append(label)
    labels, problems = [], []
    if not by_heading:
        return labels, problems  # no section labels: the headings are free
    for number, heading in body_sections(text):
        if heading.lower() == SOURCES_HEADING.lower():
            continue
        candidates = by_heading.get(heading.lower())
        if not candidates:
            problems.append((number, "'## %s' is not a section heading of the profiles %s; use one of: %s"
                             % (heading, ", ".join(profiles) or "(none)",
                                ", ".join(sorted({h for _, h in section_labels(profiles)})) or "(none)")))
            continue
        if len(candidates) > 1 and intended is not None:
            chosen = [label for label in candidates if label.lower() in {l.lower() for l in intended}]
            candidates = chosen or candidates
        if len(candidates) > 1:
            problems.append((number, "'## %s' is the heading of %s; name the profile or the intended labels"
                             % (heading, " and ".join(candidates))))
            continue
        if candidates[0] not in labels:
            labels.append(candidates[0])
    return labels, problems


def label_changes(current, wanted, profiles):
    """Section labels to add and to remove so that an issue's labels follow its body's headings.

    Only section labels of the given profiles are ever removed; role and topic
    labels are left as they are.
    """
    known = {label.lower() for label, _ in section_labels(profiles)}
    have = {label.lower() for label in current}
    want = {label.lower() for label in wanted}
    add = [label for label in wanted if label.lower() not in have]
    remove = [label for label in current if label.lower() in known and label.lower() not in want]
    return add, remove


def shipped_section_labels():
    """Lowercase names of the section labels of every profile shipped in profiles/."""
    names = set()
    for name in sorted(os.listdir(PROFILE_DIR)):
        if name.endswith(".json"):
            names.update(label.lower() for label, _ in section_labels([name[:-5]]))
    return names


def plan_section_labels(labels, body, profiles):
    """Check an issue before it gets a deliverable body, and plan its section labels.

    Returns a dict:
      stop     reasons the issue may not get a deliverable body (role labels)
      foreign  section labels on the issue from profiles other than `profiles`
      checked  False when the profiles define no section labels (nothing is changed)
      wanted, add, remove, problems  as from labels_from_headings and label_changes
    Raises ValueError for an unknown profile.
    """
    lower = {label.lower() for label in labels}
    stop = []
    for role in ("hub", "active"):
        if role in lower:
            stop.append("the issue is labeled %s; only a topic issue labeled final-record holds deliverable text" % role)
    if "final-record" not in lower:
        stop.append("the issue is not labeled final-record; label it first if it is a topic of the deliverable")
    own = {label.lower() for label, _ in section_labels(profiles)}
    foreign = [label for label in labels if label.lower() in shipped_section_labels() and label.lower() not in own]
    plan = {"stop": stop, "foreign": foreign, "checked": bool(own), "wanted": [], "add": [], "remove": [],
            "problems": []}
    if own:
        plan["wanted"], plan["problems"] = labels_from_headings(body, profiles, intended=labels)
        if not plan["problems"]:
            plan["add"], plan["remove"] = label_changes(labels, plan["wanted"], profiles)
    return plan


def label_command(repo, number, add, remove):
    command = ["issue", "edit", str(number), "--repo", repo]
    for label in add:
        command += ["--add-label", label]
    for label in remove:
        command += ["--remove-label", label]
    return command


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
    """Return the text between the resume markers, or None when the text is not a well-formed resume comment.

    Well-formed means: the first non-blank line starts with the resume heading;
    each marker occurs exactly once in the whole text; each stands alone on its
    own line at column 0, outside any fenced block, start before end. A marker
    inside a blockquote, a code span or a fenced block therefore never counts.
    """
    if body.count(RESUME_START) != 1 or body.count(RESUME_END) != 1:
        return None
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    first = next((line for line in lines if line.strip()), "")
    if not first.startswith(RESUME_HEADING):
        return None
    start = end = None
    fence = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        opening = re.match(r"^(```+|~~~+)", stripped)
        if fence is None and opening:
            fence = opening.group(1)
            continue
        if fence is not None:
            if stripped.startswith(fence) and stripped.strip(fence[0]) == "":
                fence = None
            continue
        if line.rstrip() == RESUME_START:
            start = index
        elif line.rstrip() == RESUME_END:
            end = index
    if start is None or end is None or end < start:
        return None
    return "\n".join(lines[start + 1:end]).strip("\n")
