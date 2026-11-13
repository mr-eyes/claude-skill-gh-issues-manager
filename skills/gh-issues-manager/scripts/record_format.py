"""Read the formats of the record: event comments, deliverable bodies, figure and table blocks, sources.

Python 3 standard library only. Nothing here touches GitHub; the linter, the
index and compile.py all parse the record through these functions, so they
agree on what a section, an event or a figure is.
"""

import re

import ghim

EVENT_TYPES = ("result", "decision", "failure", "checkpoint", "correction", "record", "triage")
HEADED_TYPES = ("result", "decision", "failure", "checkpoint", "correction")
ISO = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})"
STAMP = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} (?:[A-Z]{2,5}|UTC[+-]\d{1,2}(?::\d{2})?)\b"
MARKER = re.compile(r"^<!-- ghim:event ((?:[a-z]+=\S+ )*[a-z]+=\S+) -->\s*$")
EVENT_HEADING = re.compile(r"^### (Result|Decision|Failure|Checkpoint|Correction|Triage)( \(reconstructed\))?: (%s) - (.+?)\s*$"
                           % STAMP)
BLOCK_HEADING = re.compile(r"^### (Figure|Table): ([A-Za-z0-9][\w.-]*) - (.+?)\s*$")
IMAGE = re.compile(r"!\[[^\]]*\]\((https://github\.com/([\w.-]+/[\w.-]+)/blob/([^/\s]+)/([^\s?)]+)\?raw=true)\)")
LINK = re.compile(r"\]\((https://github\.com/([\w.-]+/[\w.-]+)/blob/([^/\s]+)/([^\s?)#]+)[^)]*)\)")
BRANCH_REFS = {"main", "master", "head", "develop", "dev", "trunk"}
CODE_SPAN = re.compile(r"`([^`\n]+)`")
COMMIT = re.compile(r"(?<![\w/.-])(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40}(?![\w-])")
PULL = re.compile(r"(?:\bpull request\s+#(\d+)|/pull/(\d+))", re.I)
URL = re.compile(r"https?://[^\s)>|`]+")
MENTION = re.compile(r"(?<![\w/&#])#(\d{1,5})\b(?:\s*\(([^)\n]{1,60})\))?")
STOP = {"of", "the", "a", "an", "such", "that", "which", "in", "on", "for", "and", "or", "to", "with", "by", "at",
        "all", "each", "are", "is", "were", "was", "be", "its", "their", "this", "these", "those"}
NUMBER = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s+of\s+(?:the\s+)?(\d[\d,]*)\b((?:[ \t]+[A-Za-z][\w-]*){0,6})")


def parse_marker(line):
    """The fields of a `<!-- ghim:event ... -->` line as a dict, or None."""
    match = MARKER.match(line.strip())
    if not match:
        return None
    return dict(part.split("=", 1) for part in match.group(1).split())


def first_lines(text, count=2):
    lines = [line for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    return lines[:count] + [""] * (count - len(lines[:count]))


def parse_event(body):
    """What a comment is: type, times, title, as far as its text says.

    Returns a dict with type (an event type, "resume", "record" or "other"), at
    (from the marker, else None), heading_time (the stamp of the heading),
    recorded, reconstructed (bool), title and marker (the marker fields or None).
    A comment that is none of these keeps type "other"; nothing is dropped.
    """
    first, second = first_lines(body)
    marker = parse_marker(first)
    heading_line = second if marker else first
    out = {"type": "other", "at": None, "heading_time": None, "recorded": None, "reconstructed": False,
           "title": "", "marker": marker}
    if heading_line.startswith(ghim.RESUME_HEADING):
        out.update(type="resume", heading_time=heading_line[len(ghim.RESUME_HEADING):].strip() or None,
                   title="Resume block")
        return out
    if heading_line.startswith(ghim.RECORD_HEADING):
        out.update(type="record", title="Former issue body kept as history")
    match = EVENT_HEADING.match(heading_line)
    if match:
        out.update(type=match.group(1).lower(), heading_time=match.group(3), title=match.group(4),
                   reconstructed=bool(match.group(2)))
    if marker:
        # The marker types a comment only together with a matching heading; a marker alone leaves it "other".
        if out["type"] != "other" and out["type"] != marker.get("type"):
            out["type"] = "other"
        out["at"] = marker.get("at") if re.fullmatch(ISO, marker.get("at", "")) else None
        recorded = marker.get("recorded", "")
        out["recorded"] = recorded if re.fullmatch(ISO, recorded) else None
        out["reconstructed"] = out["reconstructed"] or out["recorded"] is not None
    if out["type"] == "other":
        out["title"] = re.sub(r"^#+\s*", "", heading_line)[:120]
    return out


def sections(body):
    """The level-2 sections of a body as a list of dicts: heading, line (1-based), text."""
    lines = body.replace("\r\n", "\n").split("\n")
    found = ghim.body_sections(body)
    out = []
    for index, (number, heading) in enumerate(found):
        stop = found[index + 1][0] - 1 if index + 1 < len(found) else len(lines)
        out.append({"heading": heading, "line": number, "text": "\n".join(lines[number:stop]).strip("\n")})
    return out


def section_text(body, heading):
    for section in sections(body):
        if section["heading"].lower() == heading.lower():
            return section["text"]
    return None


def table_rows(text):
    """Rows of the first Markdown table in `text`, header and separator removed, as lists of cells."""
    rows, started = [], False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", stripped)[1:-1]]
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell):
                started = True
                continue
            if started:
                rows.append(cells)
        elif started:
            break
    return rows


def sources(body):
    """Rows of the "Sources" table: a list of dicts with statement and source."""
    text = section_text(body, ghim.SOURCES_HEADING) or ""
    return [{"statement": row[0], "source": " | ".join(row[1:])} for row in table_rows(text) if row]


def refs(text):
    """Paths, commits, pull requests and URLs named in a piece of text, as (kind, value) pairs."""
    found = []
    for span in CODE_SPAN.findall(text):
        if "/" in span or re.search(r"\.\w{1,5}$", span):
            found.append(("path", span.strip()))
    for match in COMMIT.finditer(text):
        found.append(("commit", match.group(0)))
    for match in PULL.finditer(text):
        found.append(("pull", match.group(1) or match.group(2)))
    for match in URL.finditer(text):
        found.append(("url", match.group(0).rstrip(".,;")))
    for match in IMAGE.finditer(text):
        found.append(("path", match.group(4)))
        found.append(("commit" if COMMIT.fullmatch(match.group(3)) else "ref", match.group(3)))
    seen, out = set(), []
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def blocks(body):
    """Figure and table blocks: `### Figure: <id> - <title>` or `### Table: ...` inside a section.

    Each is a dict: kind, id, title, section, line, caption, image (URL), repo,
    ref, path, has_table, source (the Sources row naming it, or None), data,
    command.
    """
    lines = body.replace("\r\n", "\n").split("\n")
    rows = sources(body)
    out, current_section = [], None
    headings = {number: heading for number, heading in ghim.body_sections(body)}
    for index, line in enumerate(lines):
        if index + 1 in headings:
            current_section = headings[index + 1]
        match = BLOCK_HEADING.match(line)
        if not match:
            continue
        end = index + 1
        while end < len(lines) and not re.match(r"^#{1,3} ", lines[end]):
            end += 1
        text = "\n".join(lines[index + 1:end])
        image = IMAGE.search(text)
        link = image or LINK.search(text)
        caption = "\n".join(l for l in text.split("\n")
                            if l.strip() and not l.strip().startswith(("|", "![")) and not IMAGE.search(l)).strip()
        kind, ident = match.group(1).lower(), match.group(2)
        source = next((row for row in rows if re.search(r"\b%s %s\b" % (kind, re.escape(ident)), row["statement"], re.I)),
                      None)
        data = command = ""
        if source:
            spans = re.findall(r"(data|command)\s+`([^`]+)`", source["source"], re.I)
            data = "; ".join(value for name, value in spans if name.lower() == "data")
            command = "; ".join(value for name, value in spans if name.lower() == "command")
        out.append({
            "kind": kind, "id": ident, "title": match.group(3), "section": current_section, "line": index + 1,
            "caption": caption, "image": image.group(1) if image else (link.group(1) if link else ""),
            "repo": link.group(2) if link else "", "ref": link.group(3) if link else "",
            "path": link.group(4) if link else "", "has_table": bool(table_rows(text)), "source": source,
            "data": data, "command": command,
        })
    return out


def numbers(body):
    """Candidate quantities "<value> of <denominator> <phrase>" in the text sections, for consistency review."""
    out = []
    for section in sections(body):
        if section["heading"].lower() == ghim.SOURCES_HEADING.lower():
            continue
        for sentence in re.split(r"(?<=[.;])\s+|\n+", section["text"]):
            for match in NUMBER.finditer(sentence):
                words = [w.lower() for w in match.group(3).split() if w.lower() not in STOP]
                out.append({"section": section["heading"], "value": match.group(1).replace(",", ""),
                            "denominator": match.group(2).replace(",", ""), "phrase": " ".join(words[:3]),
                            "sentence": sentence.strip()[:300]})
    return out


def mentions(body):
    """`#N` pointers outside code, as dicts: target, cited (the text in parentheses after it, if any), line."""
    out, fence = [], None
    for number, line in enumerate(body.replace("\r\n", "\n").split("\n"), 1):
        stripped = line.strip()
        opening = re.match(r"^(```+|~~~+)", stripped)
        if fence is None and opening:
            fence = opening.group(1)
            continue
        if fence is not None:
            if stripped.startswith(fence) and stripped.strip(fence[0]) == "":
                fence = None
            continue
        line = re.sub(r"`[^`\n]*`", " ", line)
        for match in MENTION.finditer(line):
            if len(match.group(1)) == 6:
                continue
            out.append({"target": int(match.group(1)), "cited": (match.group(2) or "").strip(), "line": number})
    return out
