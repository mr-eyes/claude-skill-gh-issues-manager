# Catching up when the record starts mid-project

> Commands on this page write `scripts/<name>` for short. That is the `scripts` folder of this skill, next to `SKILL.md`; call it by its full path.

A project that installs the plugin after months of work can reach the same state as one that kept the record from the first day: deliverable text in the bodies, and a dated history in which later reconstruction is marked as such.

## 1. Discovery

When the plugin is installed and a session starts in the top folder of a git checkout with a GitHub remote but without `.recortex.json`, the SessionStart hook prints one fixed line, once per project: the plugin is installed, the project has no record yet, and the user can ask to set up the record or to catch up. It reads no project file and makes no network call. Turn it off with `GHIM_DISCOVERY=off` or `{"discovery": false}` in `~/.config/recortex/settings.json`.

## 2. Inventory (read-only)

`python3 scripts/catchup.py inventory --out .tmp/catchup/inventory` lists what exists, with dates and sizes: commits, tags and branches; merged pull requests and issues on GitHub (`--offline` skips them; `snapshot.py` gives their full text); project documents (README, CHANGELOG, CLAUDE.md, `docs/`, `notes/`); result and figure folders. With `--transcripts`, and only when the user has agreed, it also lists this project's local Claude Code session transcripts and memory files by path, date and size; it reads none of their contents. Reading transcripts happens only in the user's session, at their request, never in a hook; only the facts drawn from them go into drafts the user reviews, never the transcripts themselves.

## 3. The proposed map

From the inventory, propose the hub and the topic map by deliverable section (the main session, or the `record-drafter` agent). The user approves or edits it before anything is posted.

## 4. Current text

Draft the topic bodies as deliverable text from the sources, then review them, exactly as in the batch workflow of [migration.md](migration.md): `record-drafter`, then `record-reviewer` per batch, then its cross-issue mode, then post with read-back.

## 5. The backfilled timeline

Past events with a dated source are posted as reconstructed event comments on their topics, in time order:

```bash
python3 scripts/catchup.py event --type result --at 2025-11-04T16:20:00+01:00 --title "first speed benchmark" \
    --source commit:4f2a9c1 --body-file .tmp/catchup/notes-4f2a9c1.md --out .tmp/catchup/drafts/event-01.md
```

The draft starts with `<!-- ghim:event type=result at=<original time> recorded=<now> source=commit:4f2a9c1 -->` and the heading `### Result (reconstructed): <original time in UTC> UTC - <title>`, says when and from what it was recorded (the source in backticks), and holds the template's fields from the body file. The linter requires `recorded=` and a `source=` of the form `commit:`, `pr:`, `issue:`, `file:` or `transcript:` for every reconstructed heading. Only events with a dated source are backfilled, and for a `commit:` source `--at` must match the commit's time within one minute; undated knowledge goes into the bodies or into one dated "Catch-up" checkpoint comment. Never invent a date or a decision quote: a decision is quoted only when a `>` block stands directly under its `**Exact words:**` line; without one, `catchup.py event` writes it as "Decision inferred from <source>" and fills `**Exact words:**` with "Not recorded", and it refuses a body that has both.

`compile.py` and the index treat reconstructed events like any other, ordered by their original time, with the `reconstructed` column of `timeline.tsv` set, so the history is complete and honest about what was recorded later.

## 6. Gap catch-up on an existing record

For a stretch when the record was not kept (no sessions, or the plugin disabled), `python3 scripts/catchup.py gap` lists the commits, merged pull requests and changed files after the newest recorded event in the index. The `record-auditor` agent reports the same gap; the main session backfills it as above.
