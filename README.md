# gh-issues-manager

A Claude Code skill that keeps a project's whole record in GitHub issues: what was done, why, what was found, what was decided, what failed and where the files are. The issues are organized so that a new Claude session, or one whose context has been compacted many times, can rebuild the state of the project from GitHub alone, and so that whoever writes the final paper, release or report finds everything there.

It works for software development, research and development, scientific prototyping and manuscript preparation, alone or mixed.

## What it sets up

| Piece | What it is |
|---|---|
| Hub issue | One pinned issue that is the entry point. It holds a short "Resume here" block, the project statement, a Mermaid map, one table per section of the deliverable, a table saying which run each headline number comes from, the pull requests, the labels and the recording rules |
| Final-record issues | One self-contained issue per topic with fixed sections: current state, methods and settings, results, decisions, negative results and limitations, not established, open work, code and evidence, provenance, related topics |
| Event comments | Dated comments on the topic issue for each result, decision, failure, checkpoint and correction, written from templates |
| Active tasks | Issues labeled `active` for bounded work; each names the topic its result goes to |
| Labels | Role labels, deliverable-section labels per project type, and topic labels |

When a conclusion changes, the topic's current state is edited and the replaced text is kept in a folded block with its date. Posted comments are never rewritten.

## Who it is for

Anyone who works on a project with Claude Code over weeks or months and does not want the project's memory to live in chat transcripts. It was designed for a researcher who also writes software, and the templates lean toward that: numbers carry denominators and source paths, decisions are quoted word for word, and every record has a "not established" section.

## Requirements

- Claude Code
- The GitHub CLI `gh`, authenticated (`gh auth status`)
- Python 3.8 or newer and bash; no other packages

## Install

### As a plugin (includes the session hook)

```bash
claude plugin marketplace add mr-eyes/claude-skill-gh-issues-manager
claude plugin install gh-issues-manager@mr-eyes-skills
```

The skill is then available as `/gh-issues-manager:gh-issues-manager`, and Claude loads it on its own when a task matches. The plugin's SessionStart hook is active in every project but prints nothing unless the project has a `.gh-issues-manager.json` file.

### As a plain skill

```bash
git clone https://github.com/mr-eyes/claude-skill-gh-issues-manager
cp -r claude-skill-gh-issues-manager/skills/gh-issues-manager ~/.claude/skills/
```

Use `<project>/.claude/skills/` in place of `~/.claude/skills/` to install it for one project only. The skill is then available as `/gh-issues-manager`. The hook is optional in this mode; see below.

## First use

### A new project

Open Claude Code in the project and say something like "set up the issue tracker for this project with gh-issues-manager". Claude will:

1. Ask for the repository, the kind of project, the sections of the deliverable, the first topics, the time zone to write times in, and whether any data is restricted.
2. Write `.gh-issues-manager.json` at the project root.
3. Create the labels (`setup_labels.py`, dry run first).
4. Draft the hub and one final record per topic from the templates, lint them, and create them with `create_issues.py`, which fills in the issue numbers, pins the hub and reads every body back to confirm it.
5. Offer the CLAUDE.md snippet and the hook.

### A project with an older tracker

Say "migrate the issues of owner/old-tracker into the new structure". Claude snapshots the old tracker to local Markdown, maps every old issue and pull request to a topic, shows you the map, copies the content into self-contained new issues, and, if you want, leaves one short pointer comment on each old item. Nothing in the old tracker is edited or deleted.

## The daily loop

1. **Start.** The session reads the hub's resume block, then the open `active` issues, then the newest comments of the topics in play. With the hook this begins automatically.
2. **Work.** When an experiment finishes, a decision is made, something fails or a change is merged, the session drafts a comment from the matching template, checks every number against its source file, lints the draft and posts it. The script reads the comment back from GitHub and compares it with the draft.
3. **A conclusion changes.** The topic's current state and the hub rows are updated; the old text is kept in a folded block.
4. **Stop.** The session posts a checkpoint on each active issue and rewrites the resume block.

## What survives compaction, and why

Compaction replaces a long conversation with a summary. Summaries drop detail and sometimes get numbers and decisions wrong, so this skill never treats one as a source.

| What | Where it lives | How it comes back |
|---|---|---|
| Current focus, active issues, last decisions, next actions, holds | The hub's resume block | Printed into context by the hook after every compaction, or read with `resume_block.py show` |
| Work in flight | Checkpoint comments on `active` issues | Read in step 2 of the session protocol |
| Results, decisions, failures | Dated comments on topic issues | Read on demand; nothing depends on remembering them |
| Present conclusions and their numbers | "Current state" of each final record and the hub's number-sources table | Read before acting or writing |
| The rules themselves | The skill, and optionally the project's CLAUDE.md | Loaded by Claude Code |

The resume block is small on purpose (under 4,000 characters) and is rewritten at the end of every working stretch, so the first thing a blank session reads is short, current and written for exactly that reader.

## The optional hook and CLAUDE.md snippet

**Hook.** `scripts/session_start_hook.sh` runs on the SessionStart event for the `startup`, `resume` and `compact` sources and prints the resume block plus the list of open active issues; Claude Code adds that output to the session context. It exits quietly, printing nothing, when the project has no configuration file, when `gh` is missing or offline, or when GitHub does not answer within 10 seconds. The plugin installs it. For a plain skill install, merge [`templates/settings-hook-snippet.json`](skills/gh-issues-manager/templates/settings-hook-snippet.json) into `.claude/settings.json` or `~/.claude/settings.json` and adjust the path.

**CLAUDE.md snippet.** [`templates/claude-md-snippet.md`](skills/gh-issues-manager/templates/claude-md-snippet.md) is a few lines for the project's CLAUDE.md that give every session the hub's location and the recording rules.

## Scripts

All are in `skills/gh-issues-manager/scripts/`, use only the Python standard library and `gh`, and accept `--help`.

| Script | What it does | Writes to GitHub |
|---|---|---|
| `setup_labels.py` | Creates the labels of the chosen profiles. Existing labels are left alone unless `--update` | yes |
| `lint_drafts.py` | Checks drafts: required sections, leftover placeholders, bare `#N`, body length, Mermaid rules, secrets, project-defined restricted patterns | no |
| `create_issues.py` | Creates interlinked issues and comments from a manifest, replaces `NEW-<key>` placeholders with real numbers, reads every body back, can be rerun after a failure | yes |
| `post_verified.py` | Posts one comment or replaces one issue body, with lint, a backup of the replaced body and read-back | yes |
| `resume_block.py` | Shows or updates the hub's resume block, touching nothing else in the hub | `update` only |
| `snapshot.py` | Saves all issues, pull requests and comments as local Markdown with an index, for offline reading and for surveying an old tracker | no |
| `session_start_hook.sh` | The SessionStart hook | no |

Every script that writes has `--dry-run`, which prints the exact `gh` commands and changes nothing.

## Safety rules

- No script deletes an issue, a comment or a label, edits a posted comment, or closes an issue.
- Only files named on the command line or in a manifest are posted. Nothing is posted by folder or wildcard.
- Every write is read back from the API and compared with the draft.
- The linter refuses drafts that contain common token formats or match the project's `restricted_patterns`, for example participant identifiers.
- Decisions are quoted word for word with date, time and zone.
- An older tracker is never edited; at most it receives short pointer comments.

## Worked example

`examples/tinycsv/` holds the drafts for an invented project: a small CSV library preparing release 0.3.0, with a benchmark note. It has a hub, two topics, one active task, one result and one decision.

```bash
cd examples/tinycsv
S=../../skills/gh-issues-manager/scripts

python3 $S/setup_labels.py --dry-run
python3 $S/lint_drafts.py --manifest manifest.json
python3 $S/create_issues.py --manifest manifest.json --dry-run
```

The dry run prints what would happen, for example:

```text
manifest: manifest.json   repository: example-org/tinycsv   issues: 4   comments: 2
lint: all 6 drafts pass
dry run: no network access, nothing written
would run: gh issue create --repo example-org/tinycsv --title 'tinycsv project hub' --body-file - --label hub   # body: a one-line stub, replaced in the next step
would run: gh issue edit '<number of NEW-hub>' --repo example-org/tinycsv --body-file -   # hub.md, 4423 characters, with NEW-reader, NEW-speed, NEW-task-newlines replaced by real numbers
would read back: gh api repos/example-org/tinycsv/issues/<number of NEW-hub> and compare with hub.md
would run: gh issue pin '<number of NEW-hub>' --repo example-org/tinycsv
...
```

In the drafts, issues refer to each other as `NEW-reader`, `NEW-speed` and so on. After a real run in an empty repository those become `#2`, `#3` and so on (`Issue 2` inside the Mermaid map), and the hub's resume block reads:

```text
**Last updated:** 2026-03-04 16:40 PST by the maintainer's Claude session
**Current focus:** Release 0.3.0. The reader handles quoted fields; newlines inside quoted fields are the last open item.
**Active issues:** #4 (newlines inside quoted fields).
**Last decisions:** 2026-03-04 15:55 PST, strict quoting is the default, see #2.
```

To try a real run, change `repo` in `manifest.json` and `.gh-issues-manager.json` to a scratch repository of your own.

## Repository layout

```text
.claude-plugin/           plugin.json and marketplace.json
hooks/hooks.json          SessionStart hook registration for the plugin
skills/gh-issues-manager/
  SKILL.md                the skill
  references/             detail loaded on demand
  templates/              hub, final record, active task, comments, snippets
  profiles/               label sets per project type
  scripts/                the helpers
examples/tinycsv/         invented example project
tests/                    offline tests with a local stand-in for gh
```

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests never contact GitHub.
