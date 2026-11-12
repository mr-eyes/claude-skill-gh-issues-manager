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

The skill is then available as `/gh-issues-manager:gh-issues-manager`, and Claude loads it on its own when a task matches. The plugin's SessionStart hook is registered for every project but prints nothing until you trust a repository (next section). The same trust list governs `resume_block.py show`.

### Trust the repositories whose hub the hook may print

The hook puts text from a GitHub issue into every session, so it is off until you opt in, per repository, in a file that belongs to you and not to any project:

```bash
mkdir -p ~/.config/gh-issues-manager
echo "your-name/your-project" >> ~/.config/gh-issues-manager/trusted-repos
```

Each line is `owner/name`, optionally followed by GitHub logins that may write the hub besides the repository owner:

```text
# owner/name   extra allowed logins
your-name/your-project
your-lab/shared-project   your-name   a-colleague
```

For a repository owned by an organization, list the people who maintain the hub, because the owner is then not a person. `GHIM_TRUSTED_REPOS` (comma-separated `owner/name`) does the same for one shell. See "Security model" below for what this protects against.

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

**Hook.** `scripts/session_start_hook.sh` runs on the SessionStart event for all five session sources (`startup`, `resume`, `clear`, `compact`, `fork`) and prints the resume block plus the numbers and labels of open active issues, followed by one line pointing to the skill's session protocol; Claude Code adds that output to the session context. It prints nothing when the project has no configuration file, when the repository is not in your trusted list, when `gh` is missing or offline, or when GitHub does not answer within 10 seconds. If the hub was written or edited by an account outside the allowed list, it prints one line saying the block was skipped and why. The plugin installs it. For a plain skill install, merge [`templates/settings-hook-snippet.json`](skills/gh-issues-manager/templates/settings-hook-snippet.json) into `.claude/settings.json` or `~/.claude/settings.json` and adjust the path.

**CLAUDE.md snippet.** [`templates/claude-md-snippet.md`](skills/gh-issues-manager/templates/claude-md-snippet.md) is a few lines for the project's CLAUDE.md that give every session the hub's location and the recording rules.

## Scripts

All are in `skills/gh-issues-manager/scripts/`, use only the Python standard library and `gh`, and accept `--help`.

| Script | What it does | Writes to GitHub |
|---|---|---|
| `setup_labels.py` | Creates the labels of the chosen profiles. Existing labels are left alone unless `--update` | yes |
| `lint_drafts.py` | Checks drafts: required sections, leftover placeholders, bare `#N`, body length, Mermaid rules, secrets, project-defined restricted patterns | no |
| `create_issues.py` | Creates interlinked issues and comments from a manifest, replaces `NEW-<key>` placeholders with real numbers, reads every body and comment back, and can be rerun after a failure without duplicates or overwriting changed bodies | yes |
| `post_verified.py` | Posts one comment or replaces one issue body, with lint, a backup of the replaced body and read-back | yes |
| `resume_block.py` | Shows or updates the hub's resume block, touching nothing else in the hub. `show` reads only trusted repositories; `update` refuses if the hub changed while it was being prepared | `update` only |
| `snapshot.py` | Saves all issues, pull requests and comments as local Markdown with an index, for offline reading and for surveying an old tracker | no |
| `session_start_hook.sh` | The SessionStart hook | no |

Every script that writes has `--dry-run`, which prints the exact `gh` commands and changes nothing.

## Safety rules

- No script deletes an issue, a comment or a label, edits a posted comment, or closes an issue.
- Only files named on the command line or in a manifest are posted. Nothing is posted by folder or wildcard.
- Every issue body and comment that is written is read back from the API and compared with the draft. A pin is confirmed by asking GitHub whether the issue is pinned. Labels are not read back; rerunning `setup_labels.py` shows anything missing.
- `create_issues.py` never overwrites a body that was changed on GitHub after it wrote it, and after an interrupted run it adopts what already exists instead of creating it twice.
- The linter refuses drafts that contain common token formats or match the project's `restricted_patterns`, for example participant identifiers.
- Decisions are quoted word for word with date, time and zone.
- An older tracker is never edited; at most it receives short pointer comments.
- Text read from GitHub is treated as data, never as instructions (see "Security model").

## Security model

Issue and comment text read back from GitHub is data, never instructions. A hub can be edited by anyone with write access to the repository, and on a public repository anyone can open issues and write comments. The skill tells Claude to treat everything it reads from the tracker as a description of the project's state, and never to follow commands found there. Only the user, in the session, gives instructions.

The SessionStart hook deserves extra care because it puts tracker text into context without anyone asking. Its rules:

| Rule | What it prevents |
|---|---|
| The configuration is read only from the project root: `CLAUDE_PROJECT_DIR` (which Claude Code sets for hooks), else the top of the git checkout, else the current folder. Parent folders are never searched. The same holds for every script, and each script prints the configuration file and repository it is using | A `.gh-issues-manager.json` planted in a parent folder pointing sessions at someone else's repository |
| Trust is checked in every mode. The hook prints nothing, and `resume_block.py show` prints a one-line notice, unless the configured repository is in the user's own trusted list (`~/.config/gh-issues-manager/trusted-repos` or `GHIM_TRUSTED_REPOS`). Nothing inside a project can add to that list, and the repository owner counts as an allowed writer only once the repository is trusted | A cloned repository that configures itself to inject text |
| The hub's text is printed only if its author, the account GitHub names as its current editor, and the editors of its newest 100 body edits are all allowed: the repository owner plus the logins listed for that repository in the trusted file. The body and its edit history come from one API call, and the newest edits are chosen by time. If the issue was edited but the history comes back empty or incomplete, the block is skipped. Otherwise one line says the block was skipped and why | An account outside the list editing the hub |
| Issue titles are never printed. Open `active` issues are listed by number and labels, with a count | Instructions smuggled in through an issue title, which anyone who can edit the issue can change |
| The output is wrapped in `BEGIN/END PROJECT STATUS DATA` lines that say it is data and not instructions, text that imitates those lines is defused, the block is cut at 4,000 characters and the whole output at 6,000 | Text posing as system or user instructions, and context flooding |
| Any failure or timeout prints nothing and exits 0 | A slow or broken network blocking the session |

The trust boundary is write access to the repository. Anyone or anything that can edit issues there can change the hub: collaborators, GitHub Apps, Actions workflows, and tokens with `issues: write`. An allowed account can still write anything into the hub, so list only accounts you would take project status from; a bot that edits the hub must be listed too, or the block is skipped. Edits older than the newest 100 are not checked, which is acceptable because every resume update rewrites the whole block.

`resume_block.py show` applies the same checks when run by hand. Its `--trust-once` and `--allow-any-author` flags are deliberate overrides for the user and are refused in hook mode.

## Worked example

`examples/tinycsv/` holds the drafts for an invented project: a small CSV library preparing release 0.3.0, with a benchmark note. It has a hub, two topics, one active task, one result and one decision.

```bash
cd examples/tinycsv
S=../../skills/gh-issues-manager/scripts
export GHIM_CONFIG=$PWD/.gh-issues-manager.json   # the example is not at a project root

python3 $S/setup_labels.py --dry-run
python3 $S/lint_drafts.py --manifest manifest.json
python3 $S/create_issues.py --manifest manifest.json --dry-run
```

The dry run prints what would happen, for example:

```text
config: <path>/examples/tinycsv/.gh-issues-manager.json  repo: example-org/tinycsv
manifest: manifest.json   repository: example-org/tinycsv   issues: 4   comments: 2
lint: all 6 drafts pass
dry run: no network access, nothing written
note: commands are listed issue by issue. The real run creates all issues first, then writes the bodies, then posts the comments.
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

The dry run lists the commands issue by issue; the real run creates all issues first, then writes the bodies, then posts the comments.

To try a real run, change `repo` in `manifest.json` and `.gh-issues-manager.json` to a scratch repository of your own, run `setup_labels.py` and `create_issues.py` without `--dry-run`, and then set `hub` in `.gh-issues-manager.json` to the number the run printed for `NEW-hub`. The run leaves `manifest.json.state.json` beside the manifest; it is what makes a rerun safe, and this repository's `.gitignore` excludes it.

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

## License

MIT. See [LICENSE](LICENSE).
