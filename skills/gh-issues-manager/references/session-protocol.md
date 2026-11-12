# Session protocol

The purpose of this protocol is that no state exists only in a session. A session can end, crash or be compacted at any moment; whatever was not on GitHub by then is lost or, worse, half-remembered.

## At session start and after every compaction

A compacted context keeps a summary written by a model under space pressure. Treat it as a rumor about the project: useful for knowing where to look, not for numbers, decisions or status.

1. **Resume block.** `python3 scripts/resume_block.py show --active`. With the SessionStart hook installed the same text is already in context, marked as read from GitHub; use it if it is from this session start.
2. **Active issues.** For every open issue labeled `active`: `gh issue view N --comments`. Read the body and at least the newest checkpoint.
3. **Hub and topics in play.** Read the hub body (`gh issue view <hub>`), then for each topic the current focus touches, the "Current state" section and the newest comments.
4. **Reality check.** Compare with what exists: `git status`, `git log`, running jobs, output files named in the newest checkpoint. A checkpoint may say "running" about something that finished or died hours ago.
5. **Act.** Say in one line what was read ("Read hub #1, active #14, topics #5 and #7; last checkpoint 2026-03-04 16:40 PST"), then continue from the resume block's next actions.

If the record and reality disagree, do not quietly follow either. Post a correction or checkpoint comment that states what was found, then continue.

If the owner gives an instruction that conflicts with the resume block's holds, the owner's new words win; record them as a decision first.

## While working

- Record each event when it happens (see SKILL.md, "Record an event"). A result that exists only in the session is one compaction away from being misquoted.
- When the owner decides something in chat, copy their words into a draft decision comment right away, while the exact text is still in context.
- Before starting a command or job that will outlive the session's attention, post a checkpoint saying what was started, where its output goes and how to tell that it finished.

## End of a working stretch

Do this before stopping, before handing over, and when the context is close to full:

1. Post a checkpoint comment on each active issue that changed since its last checkpoint.
2. Draft a new resume block from `templates/resume-block.md`:
   - Last updated: now, with zone, and who.
   - Current focus: one or two sentences.
   - Active issues: numbers with a few words each.
   - Last decisions: at most three, newest first, each with a link to its decision comment.
   - Next actions: a table of concrete steps with owners.
   - Holds: anything that must not be done or restarted without the owner's word.
3. `python3 scripts/resume_block.py update --file <draft> --dry-run`, check the diff, then run it without `--dry-run`. The script changes only the block, and reads the hub back.

Keep the block under 4,000 characters. It is an index into the record, not the record.

## The SessionStart hook

`scripts/session_start_hook.sh` prints the resume block and the list of open active issues to standard output. Claude Code adds the standard output of a SessionStart hook to the session context, and the hook is registered for the `startup`, `resume` and `compact` sources, so the block re-enters context after every compaction without anyone remembering to ask.

The hook is quiet by design: with no `.gh-issues-manager.json` in the project, no `gh`, no network, or a slow answer (default limit 10 seconds, `GHIM_HOOK_TIMEOUT` to change), it prints nothing and exits 0. An empty hook output therefore means "not read", never "nothing to do". In that case run step 1 by hand.

Install: as part of the plugin (automatic), or by adding `templates/settings-hook-snippet.json` to `.claude/settings.json` of the project or to `~/.claude/settings.json`, with the path adjusted to where the skill folder is.

## The CLAUDE.md snippet

`templates/claude-md-snippet.md` gives every session of the project the hub's location and the recording rules, whether or not the skill has been loaded yet. Fill in the repository, hub number, time zone and restricted-data rule, and add it to the project's CLAUDE.md with the owner's agreement.

## When GitHub is unreachable

Take snapshots while GitHub is reachable: `python3 scripts/snapshot.py --out <folder>` writes `INDEX.md` and one Markdown file per issue with all comments. When `gh` fails, read the newest snapshot, starting from the hub file named in the index, and tell the owner that the state comes from a copy taken at the time shown in `INDEX.md`. Write drafts as usual and post them when GitHub is back; do not treat a draft as recorded until it has been posted and read back.
