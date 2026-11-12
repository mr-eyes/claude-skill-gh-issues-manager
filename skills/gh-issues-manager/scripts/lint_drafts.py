#!/usr/bin/env python3
"""Lint issue and comment drafts before they are posted to GitHub.

Checks: required sections for the kind of draft, placeholders left in the text,
bare #N references, body length, Mermaid rules, the resume block of a hub,
verbatim quotes in decisions, secrets and project-defined restricted patterns.

Read-only. With --online it asks GitHub whether each bare #N exists; without it
no network access happens.

Examples:
  lint_drafts.py --kind final-record drafts/topic-parser.md
  lint_drafts.py --kind result --repo owner/name --online drafts/result.md
  lint_drafts.py --manifest drafts/manifest.json
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghim  # noqa: E402

FINAL_RECORD_SECTIONS = [
    "## Current state",
    "## Methods and settings",
    "## Results",
    "## Decisions",
    "## Negative results and limitations",
    "## Not established",
    "## Open work",
    "## Code and evidence",
    "## Provenance",
    "## Related topics",
]

RESUME_FIELDS = [
    "**Last updated:**",
    "**Current focus:**",
    "**Active issues:**",
    "**Last decisions:**",
    "**Next actions:**",
    "**Holds:**",
]

KINDS = {
    "hub": {
        "sections": [
            "## Resume here",
            "## Project",
            "## Map",
            "## Deliverable sections",
            "## Number sources",
            "## Pull requests",
            "## Labels",
            "## Older tracker",
            "## Recording rules",
        ],
    },
    "final-record": {"sections": FINAL_RECORD_SECTIONS},
    "active": {
        "sections": ["## Goal", "## Destination topic", "## Done when", "## Plan", "## Result"],
    },
    "result": {
        "header": "Result",
        "sections": [
            "**What ran:**",
            "**Configuration:**",
            "**Numbers:**",
            "**Exclusions and failures:**",
            "**Cost:**",
            "**Not established:**",
            "**Next step:**",
        ],
    },
    "decision": {
        "header": "Decision",
        "sections": [
            "**Decision:**",
            "**Decided by:**",
            "**Exact words:**",
            "**Where recorded:**",
            "**Effect:**",
            "**Next step:**",
        ],
    },
    "failure": {
        "header": "Failure",
        "sections": [
            "**What failed:**",
            "**What ran:**",
            "**Cause:**",
            "**Impact:**",
            "**Not established:**",
            "**Next step:**",
        ],
    },
    "checkpoint": {
        "header": "Checkpoint",
        "sections": [
            "**State:**",
            "**Done since the last checkpoint:**",
            "**In progress:**",
            "**Next actions:**",
            "**Open questions:**",
        ],
    },
    "correction": {
        "header": "Correction",
        "sections": [
            "**Corrects:**",
            "**Was:**",
            "**Is:**",
            "**Why:**",
            "**Also updated:**",
        ],
    },
    "resume": {"header": "Resume block", "sections": RESUME_FIELDS},
    "continuation": {"sections": []},
    "pointer": {"sections": []},
    "generic": {"sections": []},
}

# Date, time and zone, for example "2026-03-04 14:10 PST" or "2026-03-04 14:10 UTC+1".
STAMP = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} (?:[A-Z]{2,5}|UTC[+-]\d{1,2}(?::\d{2})?)\b"

SECRET_PATTERNS = [
    ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    ("GitHub fine-grained token", r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
    ("AWS access key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("private key block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("Slack token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    ("API key", r"\bsk-[A-Za-z0-9_-]{32,}"),
]

BARE_REF = re.compile(r"(?<![\w/&#])#(\d+)\b")
TEMPLATE_FIELD = re.compile(r"\{\{[^{}\n]*\}\}")
FENCE = re.compile(r"^\s*(```+|~~~+)(.*)$")

ARROW = re.compile(r"<?(?:-\.+->?|-{2,}[>ox]?|={2,}[>ox]?)")
NODE_ID = re.compile(r"^[A-Za-z0-9_]+$")
SKIP_PREFIXES = ("classDef ", "class ", "style ", "linkStyle ", "click ", "direction ")


class Finding:
    def __init__(self, level, code, line, message):
        self.level, self.code, self.line, self.message = level, code, line, message

    def __str__(self):
        where = "line %d" % self.line if self.line else "whole text"
        return "%s [%s] %s: %s" % (self.level.upper(), self.code, where, self.message)


def split_regions(text):
    """Yield (line_number, line, region) where region is prose, code or mermaid.

    Fence lines themselves are reported as region "fence".
    """
    fence, region = None, "prose"
    for number, line in enumerate(text.split("\n"), 1):
        match = FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)
            region = "mermaid" if match.group(2).strip().lower() == "mermaid" else "code"
            yield number, line, "fence"
            continue
        if fence is not None and match and match.group(1).startswith(fence) and not match.group(2).strip():
            fence, region = None, "prose"
            yield number, line, "fence"
            continue
        yield number, line, region


def strip_inline_code(line):
    return re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), line)


def lint_mermaid(block):
    """Check one Mermaid block. `block` is a list of (line_number, line)."""
    findings = []

    def add(level, code, line, message):
        findings.append(Finding(level, code, line, message))

    for number, line in block:
        if "#" in line:
            add("error", "mermaid-hash", number,
                "'#' inside a Mermaid block breaks rendering on GitHub; write 'Issue N'")
        if "(" in line or ")" in line:
            add("error", "mermaid-paren", number,
                "parentheses inside a Mermaid block; use [\"...\"] nodes and plain words")

    content = [(n, l.strip()) for n, l in block if l.strip() and not l.strip().startswith("%%")]
    if not content:
        add("error", "mermaid-empty", block[0][0] if block else 0, "empty Mermaid block")
        return findings
    if not re.match(r"^(flowchart|graph)\b", content[0][1]):
        return findings  # node rules below are written for flowcharts only

    defined, used, first_seen = {}, set(), {}
    for number, line in content[1:]:
        if line == "end" or line.startswith(SKIP_PREFIXES):
            continue
        if line.startswith("subgraph"):
            rest = line[len("subgraph"):].strip()
            if "[" in rest and not re.search(r'\["[^"]*"\]\s*$', rest):
                add("error", "mermaid-quote", number, "subgraph title must be double-quoted: id[\"Title\"]")
            continue
        for statement in line.split(";"):
            statement = statement.strip()
            if not statement:
                continue
            for label in re.findall(r"\|([^|]*)\|", statement):
                if not re.fullmatch(r'\s*"[^"]*"\s*', label):
                    add("error", "mermaid-quote", number, "edge label must be double-quoted: |\"%s\"|" % label.strip())
            statement = re.sub(r"\|[^|]*\|", " ", statement)
            for opener, closer in (("[", "]"), ("{", "}")):
                pattern = re.escape(opener) + r"+([^" + re.escape(opener + closer) + r"]*)" + re.escape(closer) + r"+"
                for label in re.findall(pattern, statement):
                    if not re.fullmatch(r'"[^"]*"', label.strip()):
                        add("error", "mermaid-quote", number,
                            "node label must be double-quoted: %s\"%s\"%s" % (opener, label.strip(), closer))
                statement = re.sub(pattern, "\x00", statement)
            statement = re.sub(r":::[A-Za-z0-9_-]+", "", statement)
            segments = [s.strip() for s in ARROW.split(statement)]
            is_edge = len(segments) > 1
            for segment in segments:
                for item in segment.split("&"):
                    item = item.strip()
                    if not item:
                        add("error", "mermaid-parse", number, "edge with a missing end")
                        continue
                    has_label = item.endswith("\x00")
                    node = item.rstrip("\x00").strip()
                    if not NODE_ID.match(node):
                        add("error", "mermaid-parse", number,
                            "cannot read node id %r; use letters, digits and underscores" % node)
                        continue
                    first_seen.setdefault(node, number)
                    if has_label:
                        defined.setdefault(node, number)
                    if is_edge:
                        used.add(node)
    for node, number in sorted(first_seen.items(), key=lambda kv: kv[1]):
        if node in used and node not in defined:
            add("error", "mermaid-undefined", number, "node %s is used in an edge but never given a label" % node)
        if node in defined and node not in used:
            add("error", "mermaid-unused", number, "node %s is defined but appears in no edge" % node)
    return findings


def check_sections(text, kind, template, add):
    spec = KINDS[kind]
    rows = [(n, l) for n, l, region in split_regions(text) if region == "prose"]
    header = spec.get("header")
    if header:
        first = next(((n, l) for n, l in rows if l.strip()), (0, ""))
        expected = r"^### %s: " % header
        if not re.match(expected, first[1]):
            add("error", "header", first[0], "first line must start with '### %s: <date time zone> - <title>'" % header)
        elif not (template and "{{" in first[1]) and not re.match(expected + STAMP, first[1]):
            add("error", "timestamp", first[0],
                "header needs date, time and zone, for example '### %s: 2026-03-04 14:10 PST - title'" % header)

    positions, cursor = [], 0
    for marker in spec["sections"]:
        found = None
        for index in range(cursor, len(rows)):
            line = rows[index][1].strip()
            if line == marker or line.startswith(marker + " ") or (marker.startswith("**") and line.startswith(marker)):
                found = index
                break
        if found is None:
            elsewhere = any(l.strip().startswith(marker) for _, l in rows)
            add("error", "section-order" if elsewhere else "section-missing", 0,
                "section '%s' is %s" % (marker, "out of order" if elsewhere else "missing"))
            continue
        positions.append((marker, found))
        cursor = found + 1

    if template:
        return
    everything = list(split_regions(text))
    for order, (marker, index) in enumerate(positions):
        start = rows[index][0]
        stop = rows[positions[order + 1][1]][0] if order + 1 < len(positions) else len(everything) + 1
        own = rows[index][1].strip()[len(marker):].strip()
        filled = bool(own)
        for number, line, region in everything[start:stop - 1]:
            if marker.startswith("## ") and region == "prose" and re.match(r"^#{1,2} ", line):
                break
            if line.strip() and region != "fence":
                filled = True
                break
        if not filled:
            add("error", "section-empty", start,
                "section '%s' is empty; write 'None' and why rather than leaving it blank" % marker)


def lint_text(text, kind="generic", template=False, allow_placeholders=False,
              known_keys=None, known_numbers=None, number_checker=None, config=None):
    """Return a list of Finding for one draft.

    known_numbers: set of issue numbers known to exist (offline check).
    number_checker: callable(int) -> bool used when a number is not in known_numbers.
    """
    config = config or {}
    findings = []

    def add(level, code, line, message):
        findings.append(Finding(level, code, line, message))

    if kind not in KINDS:
        add("error", "kind", 0, "unknown kind %r; choose from %s" % (kind, ", ".join(sorted(KINDS))))
        return findings

    length = len(text)
    if length > ghim.BODY_LIMIT:
        add("error", "length", 0,
            "%d characters; GitHub accepts at most %d. Split into a body plus continuation comments"
            % (length, ghim.BODY_LIMIT))
    elif length > ghim.BODY_LIMIT - 5000:
        add("warning", "length", 0, "%d characters; close to the %d limit" % (length, ghim.BODY_LIMIT))
    if not text.strip():
        add("error", "empty", 0, "draft is empty")
        return findings

    banned = [w for w in config.get("banned_words", []) if w]
    restricted = config.get("restricted_patterns", [])
    mermaid_blocks, current = [], None
    bare = {}

    for number, line, region in split_regions(text):
        if region == "mermaid":
            if current is None:
                current = []
                mermaid_blocks.append(current)
            current.append((number, line))
        else:
            current = None

        for name, pattern in SECRET_PATTERNS:
            if re.search(pattern, line):
                add("error", "secret", number, "looks like a %s; never post secrets" % name)
        for entry in restricted:
            pattern = entry.get("pattern") if isinstance(entry, dict) else entry
            label = entry.get("name", pattern) if isinstance(entry, dict) else entry
            if pattern and re.search(pattern, line):
                add("error", "restricted", number, "matches the project's restricted pattern '%s'" % label)
        for word in banned:
            if re.search(r"(?<!\w)%s(?!\w)" % re.escape(word), line, re.IGNORECASE):
                add("error", "banned-word", number, "banned word '%s'" % word)

        for match in ghim.PLACEHOLDER_RE.finditer(line):
            key = match.group(1)
            if not allow_placeholders:
                add("error", "placeholder", number, "placeholder NEW-%s is still in the text" % key)
            elif known_keys is not None and key not in known_keys:
                add("error", "placeholder-unknown", number, "NEW-%s is not a key in the manifest" % key)

        if region in ("prose", "mermaid") and not template:
            for match in TEMPLATE_FIELD.finditer(line):
                add("error", "template-field", number, "template field %s was not filled in" % match.group(0))

        if region == "prose":
            for match in BARE_REF.finditer(strip_inline_code(line)):
                if len(match.group(1)) == 6:
                    continue  # six digits after # is read as a hex color such as #123456, not as an issue
                bare.setdefault(int(match.group(1)), number)

    for block in mermaid_blocks:
        findings.extend(lint_mermaid(block))

    for ref, number in sorted(bare.items()):
        if known_numbers is not None and ref in known_numbers:
            continue
        if number_checker is not None:
            if not number_checker(ref):
                add("error", "bare-ref", number,
                    "#%d does not exist in the target repository; use owner/repo#%d or a full URL" % (ref, ref))
        elif known_numbers is not None:
            add("error", "bare-ref", number,
                "#%d is not among the known issue numbers of the target repository" % ref)
        else:
            add("warning", "bare-ref", number,
                "#%d not checked against the target repository (use --online or --known-numbers)" % ref)

    check_sections(text, kind, template, add)

    if kind == "hub":
        if ghim.RESUME_START in text or ghim.RESUME_END in text:
            add("error", "resume-in-hub", 0,
                "the resume block is a comment on the hub, not part of its body; remove the markers")
        if not mermaid_blocks:
            add("warning", "hub-map", 0, "the hub has no Mermaid map")

    if kind == "resume":
        if text.count(ghim.RESUME_START) != 1 or text.count(ghim.RESUME_END) != 1 \
                or ghim.extract_resume_block(text) is None:
            add("error", "resume-markers", 0,
                "a resume comment needs exactly one '%s' followed by one '%s'" % (ghim.RESUME_START, ghim.RESUME_END))
        else:
            findings.extend(lint_resume_block(ghim.extract_resume_block(text), template))

    if kind == "decision" and not template:
        has_quote = any(l.lstrip().startswith(">") and l.lstrip(" >").strip()
                        for _, l, region in split_regions(text) if region == "prose")
        if not has_quote and "exact words not available" not in text.lower():
            add("error", "decision-quote", 0,
                "quote the decider's exact words in a '>' block, or write 'Exact words not available' and why")

    if kind == "pointer":
        if length > 1000:
            add("error", "pointer-length", 0, "a pointer comment stays short (at most 1000 characters)")
        if "https://github.com/" not in text and not re.search(r"[\w.-]+/[\w.-]+#\d+", text) \
                and not (allow_placeholders and ghim.PLACEHOLDER_RE.search(text)):
            add("error", "pointer-link", 0, "a pointer comment must link to the new home with a full reference")

    return findings


def lint_resume_block(block, template=False):
    findings = []
    if len(block) > ghim.RESUME_LIMIT:
        findings.append(Finding("error", "resume-length", 0,
                                "resume block is %d characters; keep it under %d" % (len(block), ghim.RESUME_LIMIT)))
    for field in RESUME_FIELDS:
        if field not in block:
            findings.append(Finding("error", "resume-field", 0, "resume block lacks '%s' between the markers" % field))
    if not template:
        match = re.search(r"\*\*Last updated:\*\*\s*(.*)", block)
        if match and not re.match(STAMP, match.group(1).strip()):
            findings.append(Finding("error", "resume-timestamp", 0,
                                    "'Last updated' needs date, time and zone, for example 2026-03-04 14:10 PST"))
    return findings


def load_manifest(path):
    with open(path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    base = os.path.dirname(os.path.abspath(path))
    problems = []
    issues = manifest.get("issues", [])
    comments = manifest.get("comments", [])
    if not isinstance(issues, list) or not isinstance(comments, list):
        sys.exit("error: 'issues' and 'comments' in the manifest must be lists")
    keys = [item.get("key") for item in issues]
    for key in keys:
        if not key or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(key)):
            problems.append("issue key %r must be lowercase letters, digits and single hyphens" % key)
    if len(set(keys)) != len(keys):
        problems.append("issue keys must be unique")
    for item in issues:
        for field in ("title", "body_file", "kind", "labels"):
            if not item.get(field):
                problems.append("issue %r lacks '%s'" % (item.get("key"), field))
    for index, item in enumerate(comments):
        for field in ("issue", "body_file", "kind"):
            if not item.get(field):
                problems.append("comment %d lacks '%s'" % (index + 1, field))
        target = item.get("issue")
        if isinstance(target, str):
            match = ghim.PLACEHOLDER_RE.fullmatch(target)
            if not match or match.group(1) not in keys:
                problems.append("comment %d targets %r, which is not NEW-<key> of this manifest" % (index + 1, target))
        elif not isinstance(target, int):
            problems.append("comment %d: 'issue' must be a number or NEW-<key>" % (index + 1))
    for item in issues:
        for label in item.get("labels") or []:
            if "," in str(label):
                problems.append("label %r of issue %r contains a comma; gh would split it into two labels"
                                % (label, item.get("key")))
    files = [item.get("body_file") for item in issues + comments if item.get("body_file")]
    for name in sorted({f for f in files if files.count(f) > 1}):
        problems.append("body file %s is listed more than once; every draft is posted exactly once" % name)
    for item in issues + comments:
        name = item.get("body_file")
        if name:
            full = os.path.join(base, name)
            item["_path"] = full
            if not os.path.isfile(full):
                problems.append("body file not found: %s" % full)
    if problems:
        sys.exit("error: manifest %s\n  " % path + "\n  ".join(problems))
    return manifest


def report(path, findings, quiet=False):
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    if findings or not quiet:
        print("%s: %d error(s), %d warning(s)" % (path, len(errors), len(warnings)))
    for finding in findings:
        print("  " + str(finding))
    return len(errors)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", help="draft files to lint")
    parser.add_argument("--kind", default="generic", choices=sorted(KINDS), help="kind of draft (default: generic)")
    parser.add_argument("--manifest", help="lint every draft listed in a create_issues.py manifest")
    parser.add_argument("--repo", help="target repository, owner/name")
    parser.add_argument("--online", action="store_true", help="ask GitHub whether each bare #N exists (read-only)")
    parser.add_argument("--known-numbers", help="comma-separated issue numbers that exist in the target repository")
    parser.add_argument("--allow-placeholders", action="store_true", help="accept NEW-<key> placeholders")
    parser.add_argument("--template", action="store_true", help="lint a template: {{fields}} and empty sections are fine")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = parser.parse_args(argv)

    if not args.files and not args.manifest:
        parser.error("give draft files or --manifest")
    config = ghim.load_config()
    known = None
    if args.known_numbers:
        known = {int(x) for x in args.known_numbers.split(",") if x.strip()}
    checker = None
    if args.online:
        repo = ghim.resolve_repo(args.repo, config)
        cache = {}

        def checker(number):
            if number not in cache:
                cache[number] = ghim.number_exists(repo, number)
            return cache[number]

    jobs = [(path, args.kind, args.allow_placeholders, None) for path in args.files]
    if args.manifest:
        manifest = load_manifest(args.manifest)
        keys = {item["key"] for item in manifest.get("issues", [])}
        for item in manifest.get("issues", []) + manifest.get("comments", []):
            jobs.append((item["_path"], item["kind"], True, keys))

    total = 0
    for path, kind, allow, keys in jobs:
        findings = lint_text(ghim.read_text(path), kind=kind, template=args.template,
                             allow_placeholders=allow, known_keys=keys,
                             known_numbers=known, number_checker=checker, config=config)
        if args.strict:
            for finding in findings:
                finding.level = "error"
        total += report(path, findings)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
