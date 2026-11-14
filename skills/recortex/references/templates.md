# Templates and how to fill them

All templates are in `templates/`. Fields to fill are written `{{like this}}`; the linter rejects a draft that still contains one. Where a field does not apply, write "None" and the reason. An empty section is an error, because a reader cannot tell "nothing to report" from "forgotten". The one exception is the body of a final record: a deliverable section the topic does not feed is left out, with its label.

| Template | Kind for the linter | Use |
|---|---|---|
| `hub.md` | `hub` | The hub issue |
| `final-record.md` | `final-record` | One per topic: the deliverable's text for the topic's sections, then Sources |
| `active-task.md` | `active` | One per bounded task |
| `comment-result.md` | `result` | Finished experiment, analysis, benchmark, merged change |
| `comment-decision.md` | `decision` | A decision, quoted word for word |
| `comment-failure.md` | `failure` | A failed run, approach or change |
| `comment-checkpoint.md` | `checkpoint` | State of work in flight at the end of a stretch |
| `comment-correction.md` | `correction` | A posted statement or number was wrong |
| `comment-triage.md` | `triage` | An issue opened by hand: its type, route and what waits for confirmation |
| `recortex-triage.yml` | | The optional GitHub Actions workflow that labels issues opened without a role label |
| `resume-block.md` | `resume` | A resume comment on the hub: heading, markers and the block |
| `pointer-comment.md` | `pointer` | The short note left in an older tracker |
| `migration-map.md` | `generic` | The survey table of a migration |
| `manifest.example.json` | | The list of drafts for `create_issues.py` |
| `recortex.example.json` | | The project configuration |
| `claude-md-snippet.md` | | Lines for the project's CLAUDE.md |
| `settings-hook-snippet.json` | | The SessionStart hook for a settings file |

## Field notes

**Event marker.** The first line of every event comment: `<!-- ghim:event type=<type> at=<YYYY-MM-DDTHH:MM+HH:MM> -->`, with the type in lower case (`result`, `decision`, `failure`, `checkpoint`, `correction`) and the same local date and time as the heading, followed by its UTC offset (`date '+%Y-%m-%dT%H:%M%:z'`). The linter rejects a comment whose marker is missing or disagrees with its heading.

**Figures and tables.** In a body, a figure is a `### Figure: <id> - <title>` block inside its section: a caption with every number's denominator, then the image embedded from the commit or tag it was committed in. Its row under "Sources" starts with `Figure <id>` and gives `data` and `command` in backticks: ``| Figure read-time | data `bench/out/summary.tsv`; command `python bench/plot.py bench/out/summary.tsv`; commit 4f2a9c1 |``. A table block is the same with `### Table:` and a Markdown table or a link to a committed file. `compile.py` lists both, with their sources.

**Timestamps.** Always date, time and zone in the tracker's convention: `2026-03-04 14:10 PST`. Get it with `date '+%Y-%m-%d %H:%M %Z'`. The header of every event comment, and the heading and "Last updated" line of a resume comment, must carry one.

**Numbers.** Value, denominator, source path, every time: "41 of 53 files (`tests/conformance/report-4f2a9c1.txt`)". Open the source file and read the number from it while drafting. A percentage alone is not a number.

**What ran.** Enough to rerun or look it up: commit, command or workflow, job identifiers, output folder.

**Configuration.** Data version, code version and the settings that could change the result. If two results differ in any of these they are different runs and stay in different tables.

**Exclusions and failures.** Counts with reasons: "3 of 120 samples failed with out-of-memory, excluded". Write "None" only after checking.

**Not established.** What the result does not show. Typical entries: not tested on other inputs; cause of a failure not shown; an effect seen once; a comparison not made on the same data.

**Deliverable text.** The body of a final record is written in the deliverable's voice, as the paper, release notes or report will print it, with no "we decided", "so far" or "as of". Every number with its denominator in the sentence; its file, table, commit or tag under "Sources", and commits and tags nowhere else. One `## ` heading per deliverable section, with the heading the profile defines. A section the topic does not feed is left out, not written as "None".

**Exact words.** Copy the decider's sentence from where it was said. Keep typos. If only part is relevant, quote that part whole and mark omissions with "[...]". Never tidy up a quote. If the decision came by voice and nobody wrote it down, write "Exact words not available" and what was understood, and ask the decider to confirm in writing.

**Owner.** A name or a role, for every next step and open item. "Claude session" is a valid owner; "someone" is not.

**People.** Name or role. No pronouns inferred from names; use "they" unless the person has said otherwise.

## Placeholders for issues that do not exist yet

While drafting several issues that link to each other, write `NEW-<key>` where a number will go, with the key from the manifest (`NEW-hub`, `NEW-reader`). `create_issues.py` replaces each with `#N` in prose and with `Issue N` inside a Mermaid block, so inside Mermaid write `NEW-reader Reader`, not `Issue NEW-reader`.
