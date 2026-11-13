# gh-issues-manager

A Claude Code skill that keeps a project's whole record in GitHub issues: what was done, why, what was found, what was decided, what failed and where the files are. The issues are organized so that a new Claude session, or one whose context has been compacted many times, can rebuild the state of the project from GitHub alone, and so that the final paper, release notes or report is assembled from issue bodies that already hold its text.

It works for software development, research and development, scientific prototyping and manuscript preparation, alone or mixed.

## What it does for you

- **The record lifts the context limit.** The project's memory is its GitHub issues, not a conversation. Every session, every resumed or compacted session and every subagent starts with a short brief of where the record is and what is in play, printed by the plugin's hooks from a local index of the issues, and the rules for writing to it. Nothing important lives only in a chat.
- **The finished work compiles from the issues.** Topic bodies hold the deliverable's current text, section by section; comments hold the dated, typed history. `compile.py` writes the deliverable in the hub's order, the figure, table and source lists, and a complete dated timeline of everything that happened, tagged by the issues' labels.

Setup is a short set of questions; issues people open by hand are flagged for triage; a project that installs the plugin after months of work can catch up.

## What it sets up

| Piece | What it is |
|---|---|
| Hub issue | One pinned issue that is the entry point. It states the deliverable-text rule and holds the project statement, a Mermaid map, the issues of each deliverable section in order, the active issues, the pull requests, the labels and the recording rules. It repeats no numbers from the bodies |
| Resume comments | The short "Resume block" (current focus, active issues, last decisions, next actions, holds) is posted as a new comment on the hub at the end of every working stretch. The newest one is what a fresh session reads first; older ones stay as history |
| Topic issues | One issue per topic, labeled `final-record`. Its body is the deliverable's text for the sections it feeds (for a paper, for example `## Methods` and `## Results`), the current version only and ready to copy, followed by the sources of its numbers. Section labels such as `ms:methods` follow the body's headings |
| Event comments | Dated comments on the topic issue for each result, decision, failure, checkpoint and correction, written from templates. They are the history and never deliverable text |
| Active tasks | Issues labeled `active` for work in development and open questions; each names the topic its result goes to and carries no section label |
| Labels | Role labels, deliverable-section labels per project type, and topic labels |

When what the deliverable says changes, the topic's body is edited in place; the dated comment that caused the change and GitHub's edit history are the trail. A result that leaves the deliverable leaves the body, and its section label comes off. Posted comments are never rewritten.

## Who it is for

Anyone who works on a project with Claude Code over weeks or months and does not want the project's memory to live in chat transcripts. It was designed for a researcher who also writes software, and the templates lean toward that: numbers carry denominators and sources, decisions are quoted word for word in comments, and limitations stay in the text.

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

The skill is then available as `/gh-issues-manager:gh-issues-manager`, and Claude loads it on its own when a task matches. The plugin's hooks are registered for every project but print nothing until you trust a repository (next section). The same trust list governs `resume_block.py show`.

### Trust the repositories whose record the hooks may print

The hook puts text from a GitHub issue into every session, so it is off until you opt in, per repository, in a file that belongs to you and not to any project:

```bash
mkdir -p ~/.config/gh-issues-manager
echo "your-name/your-project" >> ~/.config/gh-issues-manager/trusted-repos
```

Each line is `owner/name`, optionally followed by GitHub logins whose resume comments you accept besides the repository owner's:

```text
# owner/name   extra allowed logins
your-name/your-project
your-lab/shared-project   your-name   a-colleague
```

A name is read only in GitHub's form, in ASCII: an owner of 1 to 39 letters, digits, `-` or `_` that starts with a letter or digit, and a name of 1 to 100 letters, digits, `.`, `-` or `_` other than `.` and `..`; a line in another form is ignored.

For a repository owned by an organization, list the people who post the resume comments, because the owner is then not a person. `GHIM_TRUSTED_REPOS` (comma-separated `owner/name`) does the same for one shell. See "Security model" below for what this protects against.

### As a plain skill

```bash
git clone https://github.com/mr-eyes/claude-skill-gh-issues-manager
cp -r claude-skill-gh-issues-manager/skills/gh-issues-manager ~/.claude/skills/
```

Use `<project>/.claude/skills/` in place of `~/.claude/skills/` to install it for one project only. The skill is then available as `/gh-issues-manager`. The hook is optional in this mode; see below.

## First use

### A new project

In a project without a record, the first session prints one line saying the plugin is installed and the project has no record yet. Say something like "set up the record for this project". Claude will:

1. Look at the project's file names (`setup.py detect`) only to pre-select answers, then ask a few questions with multiple-choice answers: what the project will produce (paper, thesis, software, dataset, report, prototype, proposal, documentation, other), the sections of each, where the record lives, who decides, the time zone, whether there is earlier work to catch up on, and the optional parts.
2. Show a summary for your confirmation; nothing is written before it.
3. Apply it (`setup.py apply`, dry run first): the configuration, the labels, the hub with its first resume comment, your trusted-list entry if you agree, the optional triage workflow and CLAUDE.md snippet, and the first sync of the local index.

### A project with months of work behind it

Say "catch up the record". Claude takes a read-only inventory of what exists (`catchup.py inventory`: history, issues, pull requests, documents, result folders, and, only if you agree, this project's local Claude Code transcripts), proposes a topic map for your approval, drafts the bodies with the plugin's agents, and posts past events as reconstructed comments with their original dates and sources.

### A project with an older tracker

Say "migrate the issues of owner/old-tracker into the new structure". Claude snapshots the old tracker to local Markdown, maps every old issue and pull request to a topic, shows you the map, copies the content into new issues (deliverable text in the bodies, history in comments), and, if you want, leaves one short pointer comment on each old item. Nothing in the old tracker is edited or deleted.

Topic bodies that hold a full record (a dated current state, folded old text, decisions, open work) are converted in place with `convert_body.py`: it checks that the live body is the one the new text was drafted from, keeps the former body as a comment, replaces the body, sets the section labels from the new headings and reads everything back.

## The daily loop

1. **Start.** The session reads the newest resume comment on the hub, then the open `active` issues, then the newest comments of the topics in play. With the hook this begins automatically.
2. **Work.** When an experiment finishes, a decision is made, something fails or a change is merged, the session drafts a comment from the matching template, checks every number against its source file, lints the draft and posts it. The script reads the comment back from GitHub and compares it with the draft.
3. **The deliverable text changes.** The topic's body is edited in place and its section labels follow its headings; the comment that caused the change is the record of why.
4. **Stop.** The session posts a checkpoint on each active issue and a new resume comment on the hub.

## What survives compaction, and why

Compaction replaces a long conversation with a summary. Summaries drop detail and sometimes get numbers and decisions wrong, so this skill never treats one as a source.

| What | Where it lives | How it comes back |
|---|---|---|
| Current focus, active issues, last decisions, next actions, holds | The newest resume comment on the hub by an allowed account | Printed into context in the record brief after every compaction, or read with `resume_block.py show` |
| Where the record is, the topics by section, active issues, issues that need triage | The hub and the issue labels, copied into a local index | The record brief at session start; a short brief in every subagent; a one-line reminder on prompts when it changed |
| Results, decisions and failures not yet posted | The conversation | The PreCompact hook tells the compaction summary to keep them, with enough detail to post them |
| Work in flight | Checkpoint comments on `active` issues | Read in step 2 of the session protocol |
| Results, decisions, failures | Dated comments on topic issues | Read on demand; nothing depends on remembering them |
| What the deliverable says now, with its numbers | The bodies of the topic issues, each number with its source | Read before acting or writing |
| The rules themselves | The skill, and optionally the project's CLAUDE.md | Loaded by Claude Code |

The resume block is small on purpose (under 4,000 characters) and a new one is posted at the end of every working stretch, so the first thing a blank session reads is short, current and written for exactly that reader. Posting it as a comment, never as an edit, also keeps a history of where the project stood at each stop.

## The agents

The plugin adds three agents for bulk and audit work, one tier below the main session, which stays the only writer to GitHub: `record-drafter` drafts topic bodies in batches to files only; `record-reviewer` reviews drafts, per batch and across all bodies; `record-auditor` checks the record for drift, untriaged issues and new deliverable signals. The drafter has no shell and no GitHub access. The reviewer and the auditor are read-only by instruction: they need Bash for read commands such as `gh issue view` and `git log`, so their tool list does not enforce it, and the main session checks what they did. Each preloads the skill and uses your default model; to choose another, copy its file into the project's `.claude/agents/` and set `model:`.

## The hooks and the CLAUDE.md snippet

**Hooks.** Four hooks keep every session and subagent aware of the record, built from a local index of the issues (`scripts/index.py`, a SQLite file under `~/.cache/gh-issues-manager` that can be rebuilt from GitHub at any time; hooks and terminal scripts use the same file):

| Hook | Prints |
|---|---|
| SessionStart (startup, resume, clear, compact, fork) | The record brief: the rules for writing to the record, the hub, the deliverable topics by section, the open active issues, the issues that need triage, and the newest allowed resume block. It syncs the index first; if GitHub does not answer in time it prints the brief from the index and says how old it is |
| SubagentStart | A short brief for the subagent: where the record is, the issues in play, and that it reads the record for facts and posts only when its task says so |
| UserPromptSubmit | One line with the hub and the active issues, only when it changed or every tenth prompt (`"prompt_hook": {"enabled": false}` in `.gh-issues-manager.json` turns it off) |
| PreCompact | Instructions for the compaction summary: keep the issue numbers in play and every result, decision or failure that is not yet posted |

They print nothing when the project has no configuration file or the repository is not in your trusted list, and never write to GitHub. Set-up builds the index once (`index.py sync`); otherwise the first session builds it in the background and the brief arrives with its next prompt. In a project that is set up and trusted, a brief that cannot be produced is replaced by one line naming the reason. `python3 scripts/hooks.py --print` shows each payload and its size; `python3 scripts/hooks.py --doctor` shows why a brief is or is not shown: configuration, trust, storage folders with owner and mode, the index and the last sync failure. The plugin installs them. For a plain skill install, merge [`templates/settings-hook-snippet.json`](skills/gh-issues-manager/templates/settings-hook-snippet.json) into `.claude/settings.json` or `~/.claude/settings.json` and adjust the paths.

**CLAUDE.md snippet.** [`templates/claude-md-snippet.md`](skills/gh-issues-manager/templates/claude-md-snippet.md) is a few lines for the project's CLAUDE.md that give every session the hub's location and the recording rules.

## Scripts

All are in `skills/gh-issues-manager/scripts/`, use only the Python standard library and `gh`, and accept `--help`.

| Script | What it does | Writes to GitHub |
|---|---|---|
| `setup_labels.py` | Creates the labels of the chosen profiles. Existing labels are left alone unless `--update` | yes |
| `lint_drafts.py` | Checks drafts: required sections, leftover placeholders, bare `#N`, body length, Mermaid rules, secrets, project-defined restricted patterns; history in a topic body; section headings against labels | no |
| `create_issues.py` | Creates interlinked issues and comments from a manifest, replaces `NEW-<key>` placeholders with real numbers, reads every body and comment back, and can be rerun after a failure without duplicates or overwriting changed bodies | yes |
| `post_verified.py` | Posts one comment or replaces one issue body, with lint, a backup of the replaced body and read-back; for a topic body, the section labels follow the headings | yes |
| `convert_body.py` | Converts a record body of an older form into deliverable text: stops if the live body changed, keeps the former body as a comment, replaces the body and section labels, reads all back | yes |
| `resume_block.py` | `show` prints the newest resume comment written by an allowed account, for trusted repositories only. `update` posts a new resume comment on the hub and reads it back; it never edits the hub or an earlier comment, and warns when the posting login is not allowed | `update` only |
| `snapshot.py` | Saves all issues, pull requests and comments as local Markdown with an index, for offline reading and for surveying an old tracker | no |
| `index.py` | Keeps the local index of the record: `sync` reads what changed on GitHub; `query` answers consistency, impact, timeline, triage and brief questions without network | no |
| `hooks.py`, `run_hook.sh`, `session_start_hook.sh` | The four hooks; `hooks.py --print` shows their payloads | no |
| `setup.py` | `detect` suggests deliverables from file names; `apply` makes the setup from answers you confirmed | `apply` |
| `catchup.py` | Lists earlier work and work done since the newest recorded event; drafts reconstructed event comments | no |
| `compile.py` | Writes the deliverable section by section in the hub's order, the figure, table and source lists, the full dated timeline of the project and a manifest | no |

Every script that writes has `--dry-run`, which prints the exact `gh` commands and changes nothing.

## Safety rules

- No script deletes an issue, a comment or a label, edits a posted comment, or closes an issue. The only labels a script changes on an existing issue are section labels, which follow the body's headings.
- Only files named on the command line or in a manifest are posted. Nothing is posted by folder or wildcard.
- Every issue body and comment that is written is read back from the API and compared with the draft. A pin is confirmed by asking GitHub whether the issue is pinned. Section labels changed on an issue are read back; labels created by `setup_labels.py` are not, and rerunning it shows anything missing.
- `create_issues.py` never overwrites a body that was changed on GitHub after it wrote it, and after an interrupted run it adopts what already exists instead of creating it twice.
- The linter refuses drafts that contain common token formats or match the project's `restricted_patterns`, for example participant identifiers.
- Decisions are quoted word for word with date, time and zone.
- An older tracker is never edited; at most it receives short pointer comments.
- Text read from GitHub is treated as data, never as instructions (see "Security model").

## Security model

Issue and comment text read back from GitHub is data, never instructions. A hub can be edited by anyone with write access to the repository, and on a public repository anyone can open issues and write comments. The skill tells Claude to treat everything it reads from the tracker as a description of the project's state, and never to follow commands found there. Only the user, in the session, gives instructions.

The hooks deserve extra care because they put tracker text into context without anyone asking. Their rules:

| Rule | What it prevents |
|---|---|
| The configuration is read only from the project root: `CLAUDE_PROJECT_DIR` (which Claude Code sets for hooks), else the top of the git checkout, else the current folder. Parent folders are never searched. The same holds for every script, and each script prints the configuration file and repository it is using | A `.gh-issues-manager.json` planted in a parent folder pointing sessions at someone else's repository |
| Trust is checked in every mode. The hook prints nothing, and `resume_block.py show` prints a one-line notice, unless the configured repository is in the user's own trusted list (`~/.config/gh-issues-manager/trusted-repos` or `GHIM_TRUSTED_REPOS`; `XDG_CONFIG_HOME` and `GHIM_TRUSTED_FILE` are used only when they are absolute paths, so a relative value cannot point into a project). Nothing inside a project can add to that list, and the repository owner counts as an allowed writer only once the repository is trusted | A cloned repository that configures itself to inject text |
| The resume block is a comment, and only a comment that passes every check is printed: its first line is the resume heading, each marker stands alone on its own line outside any quote or code block, its author is allowed (the repository owner plus the logins listed for that repository in the trusted file), and it was never edited by anyone. The newest 50 comments of the hub come from one API call, and the newest passing comment is chosen by creation time. Newer resume comments that fail are counted with the reason and never shown | Anyone posting or editing a comment to get text into your sessions |
| The time the shown comment was posted is printed with it | Showing an old block as if it were current. Anyone can post many comments on a public hub and push the newest resume comment beyond the 50 that are read (the script then says there is none), and an account with write access can delete the newest resume comment so that an older one is shown. Neither changes what an allowed account wrote; posting a new resume comment repairs both |
| An issue title is printed only when the issue was opened by an allowed account and no other account renamed it; otherwise only its number, with the reason | Instructions smuggled in through an issue title, which anyone who can edit the issue can change |
| The index (`index.sqlite`) and the hook state live in a folder `private/` (mode 0700) that the plugin creates inside its top folders: `$XDG_CACHE_HOME/gh-issues-manager` for the index and `$XDG_STATE_HOME/gh-issues-manager` for the state and the key (by default under `~/.cache` and `~/.local/state`); never in the project tree. Hooks, the session's Bash tool and your own shell resolve the same folders; the plugin data folder that Claude Code sets only for hooks (`CLAUDE_PLUGIN_DATA`) is not used, and an index left there by an earlier version is ignored (the first sync builds a new one). `GHIM_DATA_HOME` moves the index and the state to one folder, `$GHIM_DATA_HOME/gh-issues-manager`, and is read only when `GHIM_TESTING=1` is also set: it is for the plugin's tests only. A top folder must be a real folder owned by the user or by root; one the user owns that was created group-writable (umask 0002) is tightened to 0700, and one owned by another user is refused. `private/` and everything in it must be real folders and files owned by the user with no permissions for group or others, checked at every read and write; files are written through a fresh temporary file with mode 0600 and read without following symlinks. An index is read only when it carries the repository, the format and a mark made with a per-user key from the state folder, so a swapped folder or a file the plugin did not make is refused | A repository you clone, or a folder someone shares, planting an index or state file whose text the hooks would print |
| When the sync at session start fails, the brief says "cached, not refreshed" with its age; a cached resume block is one that passed every check when it was read, and is left out once it is older than `resume_cache_days` (default 7). Stored sync times enter a GitHub query only as plain ISO 8601 UTC times | Old or tampered cached text passed off as current, and text smuggled into an API query |
| A refused index is never read and nothing from it is printed; the next sync moves it aside and builds a new one. The hooks load only the profiles shipped with the plugin, never a profile file a project names, and `GHIM_HOOK_TIMEOUT` is read as digits only | A cloned project or a shared folder getting its own text into the brief outside the data frame |
| The output is wrapped in `BEGIN/END PROJECT STATUS DATA` lines that say it is data and not instructions, text that imitates those lines is defused, and the SessionStart brief is cut at 6,000 characters (the subagent brief at 2,500) | Text posing as system or user instructions, and context flooding |
| A failure to read the configuration prints nothing and exits 0. A failure to read GitHub, or a timeout, prints the brief from the local index with its age; in a set-up, trusted project with no usable index, one line names the reason and points to `hooks.py --doctor`. Every hook exits 0 | A slow or broken network blocking the session |

The trust boundary is your allowed list, not write access to the repository. Anyone who can comment can post something that looks like a resume comment, and anyone with write access (collaborators, GitHub Apps, Actions workflows, tokens with `issues: write`) can edit comments, but a comment by a non-allowed author is ignored and so is any comment that was edited after posting. Because each resume block is a single, unedited comment, the check covers everything that is printed, however long the project runs. For the same reason, never edit a resume comment yourself; post a new one. An allowed account can still write anything, so list only accounts you would take project status from, and list a bot if a bot posts the resume comments.

`resume_block.py show` applies the same checks when run by hand. Its `--trust-once` and `--allow-any-author` flags are deliberate overrides for the user and are refused in hook mode.

## Worked example

`examples/tinycsv/` holds the drafts for an invented project: a small CSV library preparing release 0.3.0, with a benchmark note. It has a hub with its first resume comment, two topics whose bodies are release-notes and benchmark-note text, one active task, one result and one decision.

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
manifest: manifest.json   repository: example-org/tinycsv   issues: 4   comments: 3
lint: all 7 drafts pass
dry run: no network access, nothing written
note: commands are listed issue by issue. The real run creates all issues first, then writes the bodies, then posts the comments.
would run: gh issue create --repo example-org/tinycsv --title 'tinycsv project hub' --body-file - --label hub   # body: a one-line stub, replaced in the next step
would run: gh issue edit '<number of NEW-hub>' --repo example-org/tinycsv --body-file -   # hub.md, 5033 characters, with NEW-reader, NEW-speed, NEW-task-newlines replaced by real numbers
would read back: gh api repos/example-org/tinycsv/issues/<number of NEW-hub> and compare with hub.md
would run: gh issue pin '<number of NEW-hub>' --repo example-org/tinycsv
...
```

In the drafts, issues refer to each other as `NEW-reader`, `NEW-speed` and so on. After a real run in an empty repository those become `#2`, `#3` and so on (`Issue 2` inside the Mermaid map), and the first resume comment on the hub reads:

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
hooks/hooks.json          hook registration for the plugin (four events)
agents/                   record-drafter, record-reviewer, record-auditor
skills/gh-issues-manager/
  SKILL.md                the skill
  references/             detail loaded on demand
  templates/              hub, topic body, active task, comments, snippets
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
