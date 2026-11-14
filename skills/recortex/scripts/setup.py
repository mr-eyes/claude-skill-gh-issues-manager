#!/usr/bin/env python3
"""Set up a project's record: suggest answers, then apply the answers the user confirmed.

detect  Read-only and local. Looks at the names of files and folders at the top
        of the project (and one level down) and suggests deliverables, each
        with the evidence for it ("pyproject.toml and tests/ exist"). It only
        pre-selects answers for the setup questions; an empty project gets no
        suggestion. Nothing is read from inside files and nothing leaves the
        machine.
apply   Makes every change, from an answers file written after the user's final
        confirmation: .recortex.json, the labels, the hub and its first
        resume comment, the trusted-repository entry, the optional triage
        workflow and CLAUDE.md snippet, and a first index.py sync in the
        foreground. --dry-run prints all of it and writes nothing; a real run
        needs --yes. Run again with new answers, it adds deliverables, sections
        and labels and never removes what is there.

Answers file (JSON):
  {"repo": "owner/name",                  the repository that holds the issues
   "record": "this" | "other" | "new",     this repository, another existing one, or a new private one
   "project": "One or two plain sentences on what the project is.",
   "deliverables": [{"kind": "paper", "sections": ["Background", "Methods", ...]}, ...],
   "decision_makers": ["Sam Rivera", "@sam-rivera"],
   "timezone": "US Pacific time, written as 2026-03-04 14:10 PST",
   "topics": ["reader", "speed"],
   "catch_up": false, "read_transcripts": false,
   "triage_workflow": false, "claude_md": false,
   "prompt_hook": {"enabled": true, "every": 10},
   "trust": true}                          true: the user agreed to add the repository to their trusted list

Kinds: paper, thesis, software, dataset, report, prototype, proposal, docs,
other (with "name" and "sections").

Examples:
  setup.py detect
  setup.py apply --answers answers.json --dry-run
  setup.py apply --answers answers.json --yes
"""

import argparse
import datetime
import json
import os
import re
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recortex  # noqa: E402
import lint_drafts  # noqa: E402
import setup_labels  # noqa: E402
import storage  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "..", "templates")
KINDS = {
    "paper": ("manuscript", "Manuscript"), "thesis": ("thesis", "Thesis"), "software": ("software", "Release notes"),
    "dataset": ("dataset", "Dataset documentation"), "report": ("research", "Report"),
    "prototype": ("prototyping", "Recommendation"), "proposal": ("proposal", "Proposal"),
    "docs": ("docs", "Documentation"), "other": ("custom", None),
}
# Markers looked for by name only, at the top of the project and one level down.
SIGNALS = {
    "paper": [("*.tex", "LaTeX files"), ("*.bib", "a bibliography"), ("manuscript/", "manuscript/"),
              ("paper/", "paper/")],
    "thesis": [("thesis/", "thesis/"), ("chapters/", "chapters/"), ("dissertation*", "a dissertation file")],
    "software": [("pyproject.toml", "pyproject.toml"), ("setup.py", "setup.py"), ("package.json", "package.json"),
                 ("Cargo.toml", "Cargo.toml"), ("go.mod", "go.mod"), ("src/", "src/"), ("tests/", "tests/")],
    "dataset": [("datapackage.json", "datapackage.json"), ("dataset/", "dataset/")],
    "report": [("*.ipynb", "notebooks"), ("results/", "results/"), ("analysis/", "analysis/"),
               ("Snakefile", "a Snakefile"), ("*.nf", "Nextflow files"), ("workflow/", "workflow/")],
    "prototype": [("demo/", "demo/"), ("spike/", "spike/"), ("prototype/", "prototype/")],
    "proposal": [("proposal/", "proposal/"), ("grant/", "grant/")],
    "docs": [("docs/", "docs/"), ("mkdocs.yml", "mkdocs.yml"), ("website/", "website/")],
}
SKIP = {".git", "node_modules", ".tmp", "__pycache__", ".venv", "venv", "env", ".tox", "dist", "build"}
# Detection stops early in a large folder: names seen at the top, in each folder below it, and in all.
TOP_LIMIT, INNER_LIMIT, TOTAL_LIMIT = 300, 100, 1000
TEXT = re.compile(r"[\w .,:;()'/+&-]{1,300}")
NAME = re.compile(r"[\w .'-]{1,60}|@[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")


# ---------------------------------------------------------------- detect

def names_in(root, top_limit=TOP_LIMIT, inner_limit=INNER_LIMIT, total=TOTAL_LIMIT):
    """File and folder names at the top of `root` and one level down, without reading any file or following a
    symlink. It stops early in a large folder, so a session start stays quick; a project that large is described by
    the names it sees first."""
    found = []
    try:
        top = os.scandir(root)
    except OSError:
        return found
    with top:
        for seen, entry in enumerate(top):
            if seen >= top_limit or len(found) >= total:
                break
            if entry.name in SKIP:
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            found.append((entry.name + "/" if is_dir else entry.name, 0))
            if not is_dir:
                continue
            try:
                inner = os.scandir(entry.path)
            except OSError:
                continue
            with inner:
                for count, child in enumerate(inner):
                    if count >= inner_limit or len(found) >= total:
                        break
                    try:
                        child_dir = child.is_dir(follow_symlinks=False)
                    except OSError:
                        child_dir = False
                    found.append((entry.name + "/" + child.name + ("/" if child_dir else ""), 1))
    return found


def matches(pattern, entry):
    path = entry[0]
    base = path.rstrip("/").split("/")[-1] + ("/" if path.endswith("/") else "")
    if pattern.endswith("/") and "/" in pattern[:-1]:
        return path == pattern
    if pattern.startswith("*"):
        return not path.endswith("/") and base.endswith(pattern[1:])
    if pattern.endswith("*"):
        return base.startswith(pattern[:-1])
    return base == pattern and entry[1] == 0


def detect(root):
    """[{"kind", "profile", "evidence": [...]}]: suggestions only, with the evidence for each, in fixed words."""
    entries = names_in(root)
    out = []
    for kind, markers in SIGNALS.items():
        evidence = []
        for pattern, words in markers:
            hits = [e for e in entries if matches(pattern, e)]
            if hits:
                evidence.append(words if not pattern.startswith("*") else "%d %s file%s" % (
                    len(hits), pattern[1:], "" if len(hits) == 1 else "s"))
        if kind == "software" and evidence == ["tests/"]:
            evidence = []  # a tests folder alone does not make a software project
        if evidence:
            out.append({"kind": kind, "profile": KINDS[kind][0], "evidence": evidence})
    return out


def covered_profiles(config):
    """The shipped profiles a setup covers; malformed entries count as nothing."""
    profiles = config.get("profiles") if isinstance(config, dict) else None
    return set(recortex.profile_names(recortex.shipped_profiles(profiles if isinstance(profiles, list) else [])))


def uncovered_signals(root, config):
    """Kinds that detect() suggests but the setup does not cover: new deliverable signals."""
    covered = covered_profiles(config)
    return [s for s in detect(root) if s["profile"] not in covered]


# The kinds of deliverable the hooks have already mentioned, or that existed when the setup ran, kept in the
# repository's private state folder, which hooks and terminal scripts resolve alike. Only kind names from SIGNALS
# are kept.

def told_path(repo):
    return os.path.join(storage.folder(storage.state_top(), storage.repo_folder(repo)), "signals.json")


def read_told(path):
    try:
        told = json.loads(storage.read_file(path) or "[]")
    except ValueError:
        told = []
    return [k for k in told if k in SIGNALS] if isinstance(told, list) else []


def remember_told(repo, kinds):
    path = told_path(repo)
    told = read_told(path)
    more = told + [k for k in kinds if k in SIGNALS and k not in told]
    if more != told or storage.read_file(path) is None:
        storage.write_file(path, json.dumps(more))
    return more


# ---------------------------------------------------------------- answers

class AnswerError(ValueError):
    pass


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "section"


def check_answers(answers):
    """Validate an answers file strictly. Returns a normalized dict; raises AnswerError naming the field."""
    if not isinstance(answers, dict):
        raise AnswerError("the answers must be a JSON object")
    out = {}
    repo = answers.get("repo")
    if not recortex.valid_repo(repo):
        raise AnswerError("repo must be owner/name in GitHub's form")
    out["repo"] = repo
    record = answers.get("record", "this")
    if record not in ("this", "other", "new"):
        raise AnswerError("record must be this, other or new")
    out["record"] = record
    project = answers.get("project", "")
    if project and (not isinstance(project, str) or not TEXT.fullmatch(project)):
        raise AnswerError("project must be one or two plain sentences, at most 300 characters")
    out["project"] = project
    deliverables = answers.get("deliverables")
    if not isinstance(deliverables, list) or not 1 <= len(deliverables) <= 8:
        raise AnswerError("deliverables must list one to eight deliverables")
    out["deliverables"] = []
    seen = set()
    for item in deliverables:
        if not isinstance(item, dict) or item.get("kind") not in KINDS:
            raise AnswerError("each deliverable needs a kind: %s" % ", ".join(KINDS))
        sections = item.get("sections")
        if sections is not None and (not isinstance(sections, list) or not 1 <= len(sections) <= 20 or not all(
                isinstance(h, str) and recortex.HEADING_TEXT.fullmatch(h) for h in sections)):
            raise AnswerError("sections must list one to twenty plain headings")
        name = None
        if item["kind"] == "other":
            name = item.get("name")
            if not isinstance(name, str) or not recortex.HEADING_TEXT.fullmatch(name) or not sections:
                raise AnswerError("a deliverable of kind other needs a plain name and its sections")
        key = (item["kind"], slug(name) if name else None)
        if key in seen:
            raise AnswerError("each kind of deliverable is listed once (a second one of a kind is kind other, with its "
                              "own name): %s" % (name or item["kind"]))
        seen.add(key)
        normalized = {"kind": item["kind"], "sections": sections, "name": name}
        entry = profile_entry(normalized)
        if isinstance(entry, dict) and recortex.custom_sections(entry) is None:
            raise AnswerError("the sections of %s do not fit: each heading once (ignoring case), no \"Sources\" "
                              "(it is the sources table of every body), plain headings" % (name or item["kind"]))
        out["deliverables"].append(normalized)
    makers = answers.get("decision_makers", [])
    if not isinstance(makers, list) or not all(isinstance(m, str) and NAME.fullmatch(m) for m in makers):
        raise AnswerError("decision_makers must be names or @handles")
    out["decision_makers"] = makers
    timezone = answers.get("timezone", "")
    if timezone and (not isinstance(timezone, str) or not TEXT.fullmatch(timezone) or len(timezone) > 80):
        raise AnswerError("timezone must be plain text, at most 80 characters")
    out["timezone"] = timezone
    topics = answers.get("topics", [])
    if not isinstance(topics, list) or not all(isinstance(t, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", t)
                                               for t in topics):
        raise AnswerError("topics must be lowercase names with hyphens")
    out["topics"] = topics
    for flag in ("catch_up", "read_transcripts", "triage_workflow", "claude_md", "trust"):
        value = answers.get(flag, False)
        if not isinstance(value, bool):
            raise AnswerError("%s must be true or false" % flag)
        out[flag] = value
    hook = answers.get("prompt_hook", {"enabled": True, "every": 10})
    if not isinstance(hook, dict) or set(hook) - {"enabled", "every"} or not isinstance(hook.get("enabled", True), bool) \
            or isinstance(hook.get("every", 10), bool) or not isinstance(hook.get("every", 10), int):
        raise AnswerError("prompt_hook must be {\"enabled\": true|false, \"every\": N}")
    out["prompt_hook"] = {"enabled": hook.get("enabled", True), "every": min(100, max(1, hook.get("every", 10)))}
    return out


def section_label(prefix, heading, deliverable=None):
    """The label of one section: the profile's prefix and the heading's slug; for a deliverable of kind other, the
    deliverable's slug comes first, so two such deliverables never share a label."""
    if deliverable:
        return "%s:%s-%s" % (prefix, slug(deliverable)[:15].strip("-"), slug(heading)[:24].strip("-"))
    return "%s:%s" % (prefix, slug(heading))


def profile_entry(item):
    """The config profile entry for one deliverable: a shipped name, or a name with the sections the user chose.
    Raises AnswerError when two headings give the same label."""
    profile = KINDS[item["kind"]][0]
    if not item["sections"]:
        return profile
    prefix = recortex.profile_prefix(profile)
    defaults = {heading.lower(): label for label, heading in recortex.section_labels([profile], shipped_only=True)} \
        if profile != "custom" else {}
    sections, used = [], {}
    for heading in item["sections"]:
        label = defaults.get(heading.lower()) or section_label(prefix, heading, item.get("name"))
        if label in used:
            raise AnswerError("the headings %r and %r give the same label %s; rename one" % (used[label], heading,
                                                                                            label))
        used[label] = heading
        sections.append([label, heading])
    entry = {"name": profile, "sections": sections}
    if item.get("name"):
        entry["deliverable"] = item["name"]
    return entry


def entry_key(entry):
    """Entries are merged by profile name and, for kind other, by the deliverable's name."""
    if isinstance(entry, dict):
        return entry.get("name"), slug(entry["deliverable"]) if isinstance(entry.get("deliverable"), str) else None
    return entry, None


def merge_profiles(existing, new):
    """Existing entries first and unchanged; new profiles added; new sections appended to an existing entry."""
    out = [json.loads(json.dumps(e)) for e in existing]
    keys = [entry_key(e) for e in out]
    added = []
    for entry in new:
        key = entry_key(entry)
        name = key[0]
        if key not in keys:
            out.append(entry)
            keys.append(key)
            added.append(entry["deliverable"] if isinstance(entry, dict) and entry.get("deliverable") else name)
            continue
        if not isinstance(entry, dict):
            continue
        index = keys.index(key)
        current = out[index]
        if not isinstance(current, dict):
            current = {"name": name, "sections": [list(p) for p in recortex.section_labels([name], shipped_only=True)]}
        have = {label for label, _ in current["sections"]}
        extra = [pair for pair in entry["sections"] if pair[0] not in have]
        if extra:
            current["sections"] = current["sections"] + extra
            added.append("%s sections %s" % (entry.get("deliverable") or name, ", ".join(h for _, h in extra)))
        out[index] = current
    return out, added


def check_existing(existing):
    """The values of an existing setup that setup.py merges and prints must fit the same patterns as the answers."""
    problems = []
    if "repo" in existing and not recortex.valid_repo(existing["repo"]):
        problems.append("repo")
    if "hub" in existing and not (isinstance(existing["hub"], int) and not isinstance(existing["hub"], bool) and
                                  existing["hub"] > 0):
        problems.append("hub")
    zone = existing.get("timezone", "")
    if zone and not (isinstance(zone, str) and TEXT.fullmatch(zone) and len(zone) <= 80):
        problems.append("timezone")
    topics = existing.get("topics", [])
    if not (isinstance(topics, list) and all(isinstance(t, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", t)
                                             for t in topics)):
        problems.append("topics")
    makers = existing.get("decision_makers", [])
    if not (isinstance(makers, list) and all(isinstance(m, str) and NAME.fullmatch(m) for m in makers)):
        problems.append("decision_makers")
    profiles = existing.get("profiles", [])
    if not (isinstance(profiles, list) and len(recortex.shipped_profiles(profiles)) == len(profiles)):
        problems.append("profiles (shipped profile names, or entries with valid sections)")
    if problems:
        raise AnswerError("the existing %s has values that do not fit: %s. Fix them by hand, then run again"
                          % (recortex.CONFIG_NAME, ", ".join(problems)))


def new_config(existing, answers):
    """The merged setup. Raises AnswerError when the existing setup or the result does not fit."""
    check_existing(existing)
    config = {k: v for k, v in existing.items() if not k.startswith("_")}
    config["repo"] = answers["repo"]
    entries = [profile_entry(item) for item in answers["deliverables"]]
    config["profiles"], added = merge_profiles(config.get("profiles") or [], entries)
    if len(recortex.shipped_profiles(config["profiles"])) != len(config["profiles"]):
        raise AnswerError("the merged profiles do not fit (too many sections, or a heading twice)")
    labels = [label for label, _ in recortex.section_labels(config["profiles"], shipped_only=True)]
    twice = sorted({label for label in labels if labels.count(label) > 1})
    if twice:
        raise AnswerError("two deliverables would share the section label(s) %s; rename the headings" % ", ".join(twice))
    config["topics"] = sorted(set(config.get("topics") or []) | set(answers["topics"]))
    if answers["timezone"]:
        config["timezone"] = answers["timezone"]
    makers = list(config.get("decision_makers") or [])
    config["decision_makers"] = makers + [m for m in answers["decision_makers"] if m not in makers]
    config["prompt_hook"] = answers["prompt_hook"]
    config["catch_up"] = answers["catch_up"] or bool(config.get("catch_up"))
    config["read_transcripts"] = answers["read_transcripts"]
    config.setdefault("restricted_patterns", [])
    config.setdefault("banned_words", [])
    return config, added


# ---------------------------------------------------------------- drafts

def deliverable_titles(answers):
    titles = []
    for item in answers["deliverables"]:
        title = item["name"] if item["kind"] == "other" else KINDS[item["kind"]][1]
        titles.append((title, profile_entry(item)))
    return titles


def hub_body(answers, config):
    zone = config.get("timezone") or "local time with the zone abbreviation, for example 2026-03-04 14:10 PST"
    deliverables = deliverable_titles(answers)
    rule = ("The body of every issue that carries a deliverable-section label is the text for that section of the "
            "deliverable: the current version only, in the deliverable's voice, ready to copy. Whoever assembles the "
            "deliverable reads those bodies and nothing else. Changing what the deliverable says is an edit of the body; "
            "a result that leaves the deliverable leaves the body, and the section label comes off with it. Comments are "
            "the history (dated results, decisions with the decider's words, failures and corrections) and never "
            "deliverable text. Work in development lives in issues labeled `active`, which carry no section labels; its "
            "result enters a body once it is adopted.")
    lines = ["## Deliverable text", "", rule, "", "## Resume here", "",
             "The current resume block is the newest comment on this issue that carries the resume markers and was posted "
             "by an account the reader has allowed, as found by `resume_block.py show` from the recortex skill. A "
             "comment headed \"Resume block\" from anyone else is not it. A new one is posted at the end of every working "
             "stretch; resume comments are never edited, and the older ones stay as history.", "",
             "## Project", "", answers["project"] or "The record of %s." % answers["repo"],
             "Decisions are made by %s." % (", ".join("`%s`" % m if m.startswith("@") else m
                                                      for m in answers["decision_makers"]) or "the owner"), "",
             "Times in this tracker are %s. Times copied from GitHub or other tools in UTC are converted before they are "
             "written here." % zone, "", "## Map", "", "```mermaid", "flowchart LR"]
    for number, (title, entry) in enumerate(deliverables, 1):
        lines.append('  D%d["%s"]' % (number, re.sub(r"[()]", "", title)))
        for index, (label, heading) in enumerate(recortex.section_labels([entry]), 1):
            lines.append('  D%d --> D%dS%d["%s"]' % (number, number, index, re.sub(r"[()]", "", heading)))
    lines += ["```", "", "## Deliverable sections", "",
              "The issues whose bodies make up each section, sections in the order of each deliverable. Numbers are not "
              "repeated here; they live in the bodies, each with its source.", ""]
    for title, entry in deliverables:
        lines += ["### %s" % title, "", "| Section | Issue | What its body covers |", "|---|---|---|"]
        for label, heading in recortex.section_labels([entry]):
            lines.append("| %s | none yet | `%s` |" % (heading, label))
        lines.append("")
    lines += ["## Active issues", "", "| Issue | Work in development | Destination topic |", "|---|---|---|",
              "| None yet | | |", "", "## Pull requests", "", "| Pull request | Merged | What it changed | Topic |",
              "|---|---|---|---|", "| None yet | | | |", "", "## Labels", "", "| Label | Meaning |", "|---|---|",
              "| `hub` | This issue |",
              "| `final-record` | Topic issue: the body is current deliverable text, the comments are its history |",
              "| `active` | Work in development; names its destination topic; carries no section labels |",
              "| `triage` | Opened by hand; not yet placed in the record |",
              "| `type:` labels | What an issue opened by hand is: task, bug, question, docs, idea, data, decision needed, "
              "duplicate, out of scope |"]
    for title, entry in deliverables:
        labels = [label for label, _ in recortex.section_labels([entry])]
        lines.append("| %s | The body is %s text for that section |" % (", ".join("`%s`" % l for l in labels), title.lower()))
    lines += ["", "## Older tracker", "", "None. The record starts here.", "", "## Recording rules", "",
              "1. Every finished experiment, decision, failure and merged change becomes a dated comment on its topic "
              "issue, written from the comment templates.",
              "2. A decision is quoted word for word with date, time and zone, in a decision comment.",
              "3. Every number carries its denominator, is checked against its source before posting, and in a body has "
              "its file, table, commit or tag under \"Sources\".",
              "4. When what the deliverable says changes, the topic's body is edited in place, with no folded old text, "
              "and the event comment that caused the change is posted. Section labels follow the body's headings.",
              "5. Work in development gets an issue labeled `active` that names its destination topic.",
              "6. Every issue and pull request is labeled when opened; an issue opened by hand is triaged.",
              "7. References outside this repository are written as `owner/repo#N` or a full URL.",
              "8. A new resume comment is posted on this issue at the end of every working stretch. Resume comments are "
              "never edited.", "9. Secrets and tokens are never posted."]
    return "\n".join(lines) + "\n"


def resume_comment(answers):
    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    if not re.fullmatch(lint_drafts.STAMP, stamp):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    actions = "| Draft the first topic issues | the owner and the session | this hub |\n"
    if answers["catch_up"]:
        actions += "| Catch up on earlier work: catchup.py inventory | the session | this hub |\n"
    return ("### Resume block: %s\n\n%s\n**Last updated:** %s by the setup\n**Current focus:** Setting up the record.\n"
            "**Active issues:** none\n**Last decisions:** none\n**Next actions:**\n\n| Action | Owner | Where |\n"
            "|---|---|---|\n%s\n**Holds:** none\n%s\n" % (stamp, recortex.RESUME_START, stamp, actions, recortex.RESUME_END))


def snippet(config):
    text = recortex.read_text(os.path.join(TEMPLATES, "claude-md-snippet.md"))
    hub = config.get("hub")
    text = text.replace("{{owner/repo}}", config["repo"]).replace("{{N}}", str(hub) if hub else "(see .recortex.json)")
    text = text.replace("{{zone}}", config.get("timezone") or "the zone named in the hub")
    return text.replace('{{project rule, for example "never post participant identifiers"}}',
                        "the project's restricted patterns in .recortex.json are never posted")


# ---------------------------------------------------------------- apply

def run(command, dry, what, cwd=None):
    shown = " ".join(command)
    if dry:
        print("would run: %s   # %s" % (shown, what))
        return ""
    print("run: %s   # %s" % (shown, what))
    result = subprocess.run(command, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise SystemExit("error: %s failed:\n%s%s" % (what, result.stdout[-2000:], result.stderr[-2000:]))
    return result.stdout


def unsafe_part(base, path):
    """The first of the folders from `base` down to `path`, and `path` itself, that is a symlink or not the kind of
    file expected, or None. `base` itself may be a symlink (a project folder reached through one)."""
    base, path = os.path.abspath(base), os.path.abspath(path)
    relative = os.path.relpath(path, base)
    if relative == os.curdir or relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return path
    current = base
    parts = relative.split(os.sep)
    for number, part in enumerate(parts):
        current = os.path.join(current, part)
        if os.path.islink(current):
            return current
        last = number == len(parts) - 1
        if os.path.lexists(current) and not (os.path.isfile(current) if last else os.path.isdir(current)):
            return current
    return None


def refuse_unsafe(base, path, hint=""):
    found = unsafe_part(base, path)
    if found:
        raise SystemExit("error: not written: %s is a symlink, or not a plain file or folder; setup.py writes only plain "
                         "files in plain folders. Nothing was changed by this step%s" % (found, hint))


def outside(path, base):
    """True when `path` is not `base` or a path below it (compares whole path components)."""
    relative = os.path.relpath(os.path.abspath(path), os.path.abspath(base))
    return relative == os.pardir or relative.startswith(os.pardir + os.sep)


def new_file_mode():
    """The mode a new file gets from the user's umask: 0o666 without the umask bits."""
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


def write_text(path, text, dry, what, base):
    """Write a project file: no symlink on the way, a fresh temporary file in the same folder, then a move. An
    existing file keeps its mode; a new one gets the mode the user's umask gives."""
    refuse_unsafe(base, path)
    if dry:
        print("would write: %s   # %s, %d characters" % (path, what, len(text)))
        return
    folder = os.path.dirname(os.path.abspath(path))
    current = os.path.abspath(base)
    for part in os.path.relpath(folder, current).split(os.sep):
        if part in (os.curdir, ""):
            continue
        current = os.path.join(current, part)
        if not os.path.lexists(current):
            os.mkdir(current)
    refuse_unsafe(base, path)
    mode = stat.S_IMODE(os.lstat(path).st_mode) if os.path.lexists(path) else new_file_mode()
    descriptor, temporary = tempfile.mkstemp(dir=folder, prefix=".part-")
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        refuse_unsafe(base, path)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)  # only the temporary file this call made
        raise
    print("wrote: %s   # %s" % (path, what))


def add_trusted(repo):
    """Add a repository to the user's trusted list through a temporary file; the file keeps its mode."""
    path = recortex.trusted_file()
    if os.path.islink(path) or os.path.lexists(path) and not os.path.isfile(path):
        raise SystemExit("error: %s is a symlink or not a plain file; add %s to it by hand" % (path, repo))
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, mode=0o700, exist_ok=True)
    current = recortex.read_text(path) if os.path.isfile(path) else ""
    if current and not current.endswith("\n"):
        current += "\n"
    mode = stat.S_IMODE(os.lstat(path).st_mode) if os.path.isfile(path) else 0o600  # a new list is private
    descriptor, temporary = tempfile.mkstemp(dir=folder, prefix=".part-")
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(current + repo + "\n")
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)  # only the temporary file this call made
        raise
    return path


def apply(answers, root, dry, drafts):
    config_path = os.path.join(root, recortex.CONFIG_NAME)
    drafts_base = os.path.dirname(drafts) if outside(drafts, root) else root
    workflow = os.path.join(root, ".github", "workflows", "recortex-triage.yml")
    claude_md = os.path.join(root, "CLAUDE.md")
    # Every file this run may write is checked before anything is changed.
    refuse_unsafe(root, config_path)
    for name in ("hub.md", "resume-1.md", "manifest.json"):
        refuse_unsafe(drafts_base, os.path.join(drafts, name), "; pass --drafts <folder> to keep the hub drafts in a "
                      "plain folder elsewhere")
    if answers["triage_workflow"] and answers["record"] == "this":
        refuse_unsafe(root, workflow)
    if answers["claude_md"]:
        refuse_unsafe(root, claude_md)
    existing = {}
    if os.path.isfile(config_path):
        try:
            existing = json.loads(recortex.read_text(config_path))
        except ValueError as error:
            raise SystemExit("error: %s is not valid JSON (%s); fix it by hand" % (config_path, error))
        if not isinstance(existing, dict):
            raise SystemExit("error: %s is not a JSON object; fix it by hand" % config_path)
        if isinstance(existing.get("repo"), str) and existing["repo"].lower() != answers["repo"].lower():
            raise SystemExit("error: %s already names %s; the answers name %s. Change the setup by hand if the record "
                             "moved" % (config_path, existing["repo"], answers["repo"]))
    try:
        config, added = new_config(existing, answers)
    except AnswerError as error:
        raise SystemExit("error: %s" % error)
    print("profiles: %s" % ", ".join(recortex.profile_names(config["profiles"])))
    if existing:
        kept = [n for n in recortex.profile_names(existing.get("profiles") or [])]
        print("kept from the existing setup: %s" % (", ".join(kept) or "nothing"))
        print("added: %s" % (", ".join(added) or "nothing"))
    python = sys.executable
    scripts = HERE

    if answers["record"] == "new" and not existing.get("repo"):
        run(["gh", "repo", "create", answers["repo"], "--private", "--description", "Project record"], dry,
            "create the private repository that holds the record")

    labels = setup_labels.wanted_labels(config["profiles"], config["topics"])  # checked before anything is written
    print("config (.recortex.json):")
    print(json.dumps(config, indent=2))
    write_text(config_path, json.dumps(config, indent=2) + "\n", dry, "the project's setup", root)

    print("labels: %d (%s)" % (len(labels), ", ".join(l["name"] for l in labels)))
    run([python, os.path.join(scripts, "setup_labels.py"), "--repo", answers["repo"]], dry,
        "create the labels that are missing (%d wanted)" % len(labels), cwd=root)

    if not existing.get("hub"):
        hub = hub_body(answers, config)
        resume = resume_comment(answers)
        findings = lint_drafts.lint_text(hub, kind="hub", config=config) + \
            lint_drafts.lint_text(resume, kind="resume", config=config)
        errors = [str(f) for f in findings if f.level == "error"]
        if errors:
            raise SystemExit("error: the hub draft does not pass lint:\n  " + "\n  ".join(errors))
        manifest = {"repo": answers["repo"],
                    "issues": [{"key": "hub", "kind": "hub", "title": "Project record hub", "labels": ["hub"],
                                "body_file": "hub.md", "pin": True}],
                    "comments": [{"issue": "NEW-hub", "kind": "resume", "body_file": "resume-1.md"}]}
        print("hub draft (%d characters):" % len(hub))
        print("\n".join("  | " + line for line in hub.rstrip("\n").split("\n")))
        write_text(os.path.join(drafts, "hub.md"), hub, dry, "the hub", drafts_base)
        write_text(os.path.join(drafts, "resume-1.md"), resume, dry, "the first resume comment", drafts_base)
        write_text(os.path.join(drafts, "manifest.json"), json.dumps(manifest, indent=2) + "\n", dry, "the manifest",
                   drafts_base)
        out = run([python, os.path.join(scripts, "create_issues.py"), "--manifest", os.path.join(drafts, "manifest.json"),
                   "--repo", answers["repo"]], dry, "create and pin the hub, post the first resume comment", cwd=root)
        if not dry:
            match = re.search(r"NEW-hub -> #([0-9]+)", out)
            if not match:
                raise SystemExit("error: the hub number was not found in the output of create_issues.py")
            config["hub"] = int(match.group(1))
            write_text(config_path, json.dumps(config, indent=2) + "\n", dry, "the hub number", root)
    else:
        print("hub: #%d exists; add rows for new sections to its deliverable tables with post_verified.py body" %
              existing["hub"])
        for title, entry in deliverable_titles(answers):
            for label, heading in recortex.section_labels([entry]):
                print("  | %s | none yet | `%s` |   (%s)" % (heading, label, title))

    if answers["trust"]:
        trusted = recortex.trusted_file()
        present = answers["repo"].lower() in recortex.trusted_repos()
        if present:
            print("trusted: %s is already in %s" % (answers["repo"], trusted))
        elif dry:
            print("would add: %s to %s   # the user agreed" % (answers["repo"], trusted))
        else:
            print("added: %s to %s" % (answers["repo"], add_trusted(answers["repo"])))
    else:
        print("trusted: not changed; the hooks stay silent until the user adds %s to %s" % (answers["repo"],
                                                                                          recortex.trusted_file()))

    if answers["triage_workflow"] and answers["record"] != "this":
        print("not written: the triage labeler runs in the repository that holds the issues (%s), not in this project; "
              "commit templates/recortex-triage.yml there as .github/workflows/recortex-triage.yml" % answers["repo"])
    elif answers["triage_workflow"]:
        text = recortex.read_text(os.path.join(TEMPLATES, "recortex-triage.yml"))
        if os.path.exists(workflow) and recortex.read_text(workflow) != text:
            print("not written: %s exists with other content; compare it with templates/recortex-triage.yml" % workflow)
        else:
            write_text(workflow, text, dry, "the triage labeler workflow; commit it to turn it on", root)
    if answers["claude_md"]:
        current = recortex.read_text(claude_md) if os.path.isfile(claude_md) else ""
        if "## Project record" in current:
            print("not written: CLAUDE.md already has a Project record section")
        else:
            write_text(claude_md, (current.rstrip("\n") + "\n\n" if current else "") + snippet(config), dry,
                       "the CLAUDE.md snippet", root)

    run([python, os.path.join(scripts, "index.py"), "--repo", answers["repo"], "sync"], dry,
        "build the local index in the foreground, so the first session has a brief", cwd=root)
    present = [item["kind"] for item in detect(root)]
    if dry:
        print("would record as known: %s   # the hooks suggest only deliverables that appear later" %
              (", ".join(present) or "nothing"))
    else:
        try:
            remember_told(answers["repo"], present)
            print("recorded as known: %s" % (", ".join(present) or "nothing"))
        except (OSError, storage.StorageError) as error:
            print("not recorded: the kinds present now (%s), because the local storage was refused: %s. The hooks may "
                  "suggest them once; hooks.py --doctor shows the storage" % (", ".join(present), error))
    if answers["catch_up"]:
        print("next: catch up on earlier work (references/catch-up.md), starting with catchup.py inventory%s"
              % (" --transcripts" if answers["read_transcripts"] else ""))
    print("dry run: nothing was written" if dry else "setup applied")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("detect", help="suggest deliverables from file and folder names (read-only, local)")
    p.add_argument("--root", help="project folder (default: the project root)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("apply", help="apply confirmed answers")
    p.add_argument("--answers", required=True, help="answers file (JSON)")
    p.add_argument("--root", help="project folder (default: the project root)")
    p.add_argument("--drafts", help="folder for the hub drafts (default: <root>/.tmp/recortex-setup)")
    p.add_argument("--dry-run", action="store_true", help="print every change; write nothing")
    p.add_argument("--yes", action="store_true", help="the user confirmed the summary; make the changes")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root or recortex.project_root())
    if args.command == "detect":
        found = detect(root)
        if args.json:
            print(json.dumps(found, indent=1))
            return 0
        if not found:
            print("no suggestion: nothing in this folder points to a kind of deliverable; ask the user")
        for item in found:
            print("suggested: %s (profile %s), because %s" % (item["kind"], item["profile"], ", ".join(item["evidence"])))
        return 0
    try:
        with open(args.answers, encoding="utf-8") as handle:
            answers = check_answers(json.load(handle))
    except (OSError, ValueError) as error:
        sys.exit("error: %s" % error)
    if not args.dry_run and not args.yes:
        sys.exit("error: pass --dry-run to see the changes, or --yes once the user has confirmed them")
    return apply(answers, root, args.dry_run, os.path.abspath(args.drafts or os.path.join(root, ".tmp",
                                                                                           "recortex-setup")))


if __name__ == "__main__":
    sys.exit(main())
