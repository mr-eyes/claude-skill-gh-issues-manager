# Templates and how to fill them

All templates are in `templates/`. Fields to fill are written `{{like this}}`; the linter rejects a draft that still contains one. Where a field does not apply, write "None" and the reason. An empty section is an error, because a reader cannot tell "nothing to report" from "forgotten".

| Template | Kind for the linter | Use |
|---|---|---|
| `hub.md` | `hub` | The hub issue |
| `final-record.md` | `final-record` | One per topic |
| `active-task.md` | `active` | One per bounded task |
| `comment-result.md` | `result` | Finished experiment, analysis, benchmark, merged change |
| `comment-decision.md` | `decision` | A decision, quoted word for word |
| `comment-failure.md` | `failure` | A failed run, approach or change |
| `comment-checkpoint.md` | `checkpoint` | State of work in flight at the end of a stretch |
| `comment-correction.md` | `correction` | A posted statement or number was wrong |
| `resume-block.md` | `resume` | A resume comment on the hub: heading, markers and the block |
| `pointer-comment.md` | `pointer` | The short note left in an older tracker |
| `migration-map.md` | `generic` | The survey table of a migration |
| `manifest.example.json` | | The list of drafts for `create_issues.py` |
| `gh-issues-manager.example.json` | | The project configuration |
| `claude-md-snippet.md` | | Lines for the project's CLAUDE.md |
| `settings-hook-snippet.json` | | The SessionStart hook for a settings file |

## Field notes

**Timestamps.** Always date, time and zone in the tracker's convention: `2026-03-04 14:10 PST`. Get it with `date '+%Y-%m-%d %H:%M %Z'`. The header of every event comment, and the heading and "Last updated" line of a resume comment, must carry one.

**Numbers.** Value, denominator, source path, every time: "41 of 53 files (`tests/conformance/report-4f2a9c1.txt`)". Open the source file and read the number from it while drafting. A percentage alone is not a number.

**What ran.** Enough to rerun or look it up: commit, command or workflow, job identifiers, output folder.

**Configuration.** Data version, code version and the settings that could change the result. If two results differ in any of these they are different runs and stay in different tables.

**Exclusions and failures.** Counts with reasons: "3 of 120 samples failed with out-of-memory, excluded". Write "None" only after checking.

**Not established.** What the result does not show. Typical entries: not tested on other inputs; cause of a failure not shown; an effect seen once; a comparison not made on the same data.

**Exact words.** Copy the decider's sentence from where it was said. Keep typos. If only part is relevant, quote that part whole and mark omissions with "[...]". Never tidy up a quote. If the decision came by voice and nobody wrote it down, write "Exact words not available" and what was understood, and ask the decider to confirm in writing.

**Owner.** A name or a role, for every next step and open item. "Claude session" is a valid owner; "someone" is not.

**People.** Name or role. No pronouns inferred from names; use "they" unless the person has said otherwise.

## Placeholders for issues that do not exist yet

While drafting several issues that link to each other, write `NEW-<key>` where a number will go, with the key from the manifest (`NEW-hub`, `NEW-reader`). `create_issues.py` replaces each with `#N` in prose and with `Issue N` inside a Mermaid block, so inside Mermaid write `NEW-reader Reader`, not `Issue NEW-reader`.
