# Hooks, the local index and compile

> Commands on this page write `scripts/<name>` for short. That is the `scripts` folder of this skill, next to `SKILL.md`; call it by its full path.

The plugin keeps every session, resumed or compacted session and subagent aware of the record without anyone asking. Four hooks print a short brief; a local index lets them do that in a fraction of a second; `compile.py` turns the record into the finished deliverable and its history. GitHub stays the record throughout: the index is a copy that can be deleted and rebuilt at any time.

## The four hooks

| Hook event | Prints | Reads GitHub | Size target |
|---|---|---|---|
| `SessionStart` (startup, resume, clear, compact, fork) | The record brief: the rules for writing to the record, the hub, the deliverable topics by section (numbers and titles only), the open `active` issues, the issues that need triage, and the newest allowed resume block | Yes: it syncs the index first, within its time limit, and falls back to the index as it is, saying how old it is | under 6,000 characters |
| `SubagentStart` (every agent type) | A short brief for the subagent: where the record is, the issues in play, and the subagent rules (read the record for facts; post only when the task says so; return facts with paths, numbers with denominators and what is not established) | No | under 2,500 |
| `UserPromptSubmit` | One line: the hub, the active issues, "record events as they happen" | No | under 400 |
| `PreCompact` (manual, auto) | Instructions for the compaction summary: keep the hub and issue numbers in play, every result, decision or failure of the conversation marked posted or not, with enough detail to post it, and the next action; the record is authoritative | No | under 2,000 |

No hook can make the skill load, so each payload carries the rules itself and says to invoke the `gh-issues-manager` skill before writing anything to the record. Claude Code writes any injected text over 10,000 characters to a file and shows only a preview; the payloads stay well below that.

`UserPromptSubmit` prints its line only when the line changed since the last brief of that session, or every tenth prompt. Both are set in `.gh-issues-manager.json`:

```json
"prompt_hook": {"enabled": true, "every": 10}
```

`python3 scripts/hooks.py --print` shows the four payloads and their sizes, for the user to check. `python3 scripts/hooks.py --doctor` says why the brief is or is not shown: the configuration, the trust status, each storage folder with its owner and mode, the index and its age, the last sync failure and the payload sizes. It reads nothing from GitHub, changes nothing and never prints the key.

### Safety

Every hook prints nothing and exits 0 when the project has no `.gh-issues-manager.json` or its repository is not in the user's trusted list (see [session-protocol.md](session-protocol.md)). In a project that is set up and trusted, the SessionStart and SubagentStart hooks are never silent: when the brief cannot be produced (the local storage was refused, there is no index yet and GitHub cannot be read, any other error) they print one line, `gh-issues-manager: record brief not shown: <reason>. Run hooks.py --doctor.` The other two stay silent then. None of the hooks writes to GitHub or blocks a session.

Text that comes from GitHub or from the project sits between the `BEGIN PROJECT STATUS DATA` and `END PROJECT STATUS DATA` lines, which say it is data and not instructions; look-alike delimiters are defused and line breaks removed, and the brief is shortened to fit its size target without ever losing the END line. Outside the frame a payload prints only the plugin's own text, the trusted repository name, issue numbers, and the index time and issue links when they have the expected form. The hooks load only the profiles shipped with the plugin, never a profile file a project names, and keep only section headings and labels of a plain form. The `index.py query` text output starts with a line saying that what follows is data from GitHub, and prints each value on one cleaned line. The resume block passes the same author and edit checks as `resume_block.py show`; only a block that passed them when it was read is cached, and a cached block older than `resume_cache_days` (default 7) is left out when GitHub cannot be read. A brief built from the index after a failed sync says "cached, not refreshed" and how old it is. The index and the hook state are kept outside the project tree and are read only when the plugin made them for this user (see [session-protocol.md](session-protocol.md), "Security model"). An issue title is shown only when the issue was opened by an allowed account and no other account renamed it (the index reads each issue's rename history); otherwise the brief shows the number and "title not shown" with the reason.

### The first build and the background sync

Set-up runs `python3 scripts/index.py sync` once in the foreground, so the first session already has an index. When a session starts without a usable index (none yet, one refused and moved aside, an older format, or an empty one) the SessionStart hook does not try to build it in its few seconds: it starts a detached background sync and prints one line, `gh-issues-manager: record brief not shown: building the local index in the background (first run); the brief appears at your next prompt. Run hooks.py --doctor for status.` Subagents get the same line while the build runs. Once the index is usable, the next UserPromptSubmit hook of that session prints the full SessionStart brief once (same frame and size cap) and then goes back to its one-line reminder; the session state records that it did. An incremental sync that does not finish within the SessionStart budget also continues in the background, so a large backlog catches up without holding up sessions.

Only one background sync runs per repository: a lock file `sync.lock` in the private folder holds its process number, start time and budget, and a lock past its budget or of a process that is gone counts as stale. The sync has its own budget, `background_sync_seconds` in `.gh-issues-manager.json` (default 300, from 30 to 3600), logs to `sync.log` and records its outcome in `sync-status.json`, both in the private folder. It stores its progress page by page and issue by issue, so a sync that is stopped or killed goes on from there the next time instead of starting over. `hooks.py --doctor` shows whether a background sync is running (process number, start time), when the last one finished and with what result, and the last error line of the log.

## The local index

`scripts/index.py` keeps a SQLite file at `<CLAUDE_PLUGIN_DATA>/private/<owner>__<repo>/index.sqlite`, or, when Claude Code has not set `CLAUDE_PLUGIN_DATA`, at `$XDG_CACHE_HOME/gh-issues-manager/private/<owner>__<repo>/index.sqlite` (by default under `~/.cache`). It is never kept in the project tree, which a cloned repository controls. It is derived from GitHub and never edited by hand; how it is protected is under "Safety" above and in [session-protocol.md](session-protocol.md), "Security model".

| Command | Does |
|---|---|
| `index.py sync` | Reads the issues and comments that changed since the last sync, the timeline of each changed issue (labeled, unlabeled, renamed, closed, reopened, pinned) and its body edits, and the hub's resume block. Read-only on GitHub. `--deadline N` stops after N seconds and keeps what it has |
| `index.py sync --rebuild` | Starts from nothing; gives the same answers as an index built step by step |
| `index.py status` | Where the index is, when it was synced, what it holds |
| `index.py query consistency` | Candidates for review: the same quantity phrase with different values or denominators in different bodies; `#N` pointers to a missing issue, or written `#N (term)` where the target does not contain the term; bodies older than their newest result, decision, failure or correction; section labels that disagree with headings; figures and tables without a Sources row |
| `index.py query impact --path P` or `--commit C` | Every section, figure, table, Sources row and event comment that cites a file or a commit |
| `index.py query timeline [--issue N] [--type T] [--since D]` | Every event comment and issue event in time order |
| `index.py query triage` | Open issues with no role label (`hub`, `final-record`, `active`, `triage`) and no closed-out type (`type:duplicate`, `type:out-of-scope`): issues people opened by hand |
| `index.py query brief` | The four hook payloads |

The index holds issues, comments and issue events as GitHub returned them, and derives from them: labels (role, section, topic and `type:` labels alike), the sections of each body, events (type, time, recorded time, reconstructed or not), figure and table blocks, Sources rows, the paths, commits, pull requests and URLs each section and event cites, candidate numbers, `#N` pointers, and which body edit followed which event. Number extraction is a heuristic: the consistency query reports candidates and never changes a body.

The SessionStart hook gives the sync half of its time limit (`GHIM_HOOK_TIMEOUT`, default 10 seconds, digits only), stops calling GitHub once that is spent, and reads at most ten issue timelines and body-edit batches per session; the rest follow at the next session, and the brief is built from the index in the remaining time. On a large tracker, run `index.py sync` once by hand to fill the index. An incremental sync reads what changed since the newest time it has seen, less one minute, so items stamped in the same second are not missed; it does not see issues or comments deleted on GitHub. `index.py sync --rebuild`, and `compile.py` by default, read everything again. A comment without an event marker is ordered by the date and time of its heading, read as UTC, because a zone abbreviation does not give an offset; the marker gives the exact time.

## Compiling the deliverable and the history

`python3 scripts/compile.py --out <folder>` rebuilds the index from GitHub, so that deleted issues and comments are not compiled (`--incremental` syncs only what changed and does not see deletions; `--no-sync` uses the index as it is), and writes:

| File | Holds |
|---|---|
| `deliverable/NN-<label>.md` | For each deliverable section, in the hub's order, the text under that section's heading in each topic body that carries its label, in the hub's topic order, each under a topic heading with the issue link |
| `deliverable/figures.tsv`, `tables.tsv` | Every figure and table block: id, issue, title, section, caption, image or file at its ref, data file, command |
| `deliverable/sources.tsv` | Every Sources row with its topic |
| `history/timeline.tsv`, `timeline.md` | Every event comment and issue event in time order: time, type, issue, issue title, labels, title, author, link, recorded time, reconstructed. A comment that is not a typed event is kept with type `other` |
| `MANIFEST.json` | Repository, hub, time of compilation, time of the index, counts, and the `--ref` given |

`--dry-run` lists what would be read and written and reads nothing from GitHub. Files of the same name are replaced; nothing else in the folder is touched.
