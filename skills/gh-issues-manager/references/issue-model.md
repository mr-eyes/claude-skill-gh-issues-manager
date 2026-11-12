# The issue model

One model serves every project type. Profiles (see [profiles.md](profiles.md)) only change the label set and what counts as an event.

## Contents

- The hub
- Final-record issues
- Events
- Changing a conclusion
- Active tasks
- Labels
- Pull requests
- What goes where

## The hub

One issue, pinned, label `hub`. It is the single entry point: a reader who knows nothing opens the hub and can reach everything else. Template: `templates/hub.md`. Its sections, in order:

| Section | Holds |
|---|---|
| Resume here | A fixed note saying that the current resume block is the newest "Resume block" comment on the hub |
| Project | A short statement of the project and the tracker's time convention |
| Map | A Mermaid flowchart: deliverable sections, the topic issues that feed them, the pull requests behind the topics |
| Deliverable sections | One table per section of the deliverable, listing the topic issues that feed it |
| Number sources | Every headline number with its value, denominator, data version, code version, configuration and source path |
| Pull requests | Each pull request, when it merged, what it changed, its topic |
| Labels | The label legend |
| Older tracker | One row per item of an older tracker and its new home, or "None" |
| Recording rules | The rules for recording new work |

The resume block itself is not in the body. It is a comment on the hub, posted anew at the end of every working stretch from `templates/resume-block.md`: last updated, current focus, active issues, last decisions, next actions with owners, holds. Comments have one author each and are never edited here, which is what lets the hook check who wrote the block before showing it (see [session-protocol.md](session-protocol.md)).

The hub holds pointers and current summaries, not detail. Detail lives in the topic issues. The hub is edited in place; it has no history of its own to protect beyond the "Number sources" table, where a replaced number is moved to the topic's folded block, not silently overwritten.

The number-sources table is what prevents the most damaging error: combining numbers from different runs. Two numbers may appear in the same sentence of a deliverable only if their rows agree on data version, code version and configuration.

## Final-record issues

One issue per topic, label `final-record` plus section and topic labels. A topic is a unit that the deliverable will describe: a method, an analysis, a component, a figure, a claim. Template: `templates/final-record.md`. Fixed sections, in this order:

| Section | Holds |
|---|---|
| Current state | The conclusion now, with numbers and denominators, the versions they come from, and the date |
| Methods and settings | What was done, with which tools, versions and settings |
| Results | Tables and statements; one run per table |
| Decisions | Date and time, who decided, their exact words, where recorded |
| Negative results and limitations | What did not work, what the results do not cover |
| Not established | What has not been tested or shown, and what would settle it |
| Open work | Item, next step, owner |
| Code and evidence | Pull requests, commits, paths, job identifiers |
| Provenance | Links to every source |
| Related topics | Other topic issues and how they relate |

The test for a final record: someone who has read nothing else can write that part of the deliverable from it. If the text says "as discussed" or "see chat", it fails the test.

A body is at most 65,536 characters. When a record grows past that, keep sections one to three in the body and move long tables into continuation comments posted right after the issue is created (kind `continuation`), each starting with a line that names the section it continues.

## Events

An event is something that happened and will matter later. Each one becomes a dated comment on its topic's final record, never a new top-level issue. Five kinds, each with a template:

| Kind | When | Template |
|---|---|---|
| Result | An experiment, analysis, benchmark or test campaign finished | `templates/comment-result.md` |
| Decision | Someone with authority chose something | `templates/comment-decision.md` |
| Failure | A run, approach or change failed | `templates/comment-failure.md` |
| Checkpoint | A working stretch ends with work in flight | `templates/comment-checkpoint.md` |
| Correction | A posted statement or number was wrong | `templates/comment-correction.md` |

Every event comment starts with `### <Kind>: <date time zone> - <title>`, so the comment list of an issue reads as a timeline. A merged change is recorded as a result comment whose "What ran" names the pull request and commit.

Comments are append-only. They are the history. Nobody rewrites them.

## Changing a conclusion

The body of a final record always states the present. When the present changes:

1. Edit "Current state" (and "Results" if needed).
2. Keep the replaced text, unchanged, in a folded block directly below, newest first:

   ```
   <details>
   <summary>Replaced on 2026-03-09 11:20 PST: rerun with data v2 changed the count</summary>

   The earlier text, unchanged.

   </details>
   ```
3. Update every hub row that cites the topic.
4. Post the result, decision or correction comment that caused the change. The comment explains why; the body shows what is true now.

## Active tasks

Bounded work that does not yet belong in a record (an investigation, a refactor, a rerun) gets its own issue with label `active`. Template: `templates/active-task.md`. It must name its destination topic. Checkpoint comments go on the task while it runs. When it ends:

1. Post the outcome as a result (or failure) comment on the destination topic.
2. Write the outcome and the link to that comment into the task's "Result" section.
3. Close the task. The `active` label stays, so closed tasks remain findable; "open and labeled `active`" is the list of work in flight.
4. Post a new resume block.

A task that ends with nothing to report still gets a result: "no change, because ...".

## Labels

| Group | Labels | Use |
|---|---|---|
| Role | `hub`, `final-record`, `active`, `needs-decision`, `migrated` | What kind of issue this is |
| Deliverable section | From the profile, for example `ms:methods` or `rel:fixed` | Which part of the deliverable the issue feeds |
| Topic | `topic:<name>` | Which topic the issue or pull request belongs to |

Every issue and pull request gets its labels when it is opened. An unlabeled item is invisible to the queries the session protocol runs.

## Pull requests

Every pull request names its topic issue in its description ("Topic: #12"), carries the topic label, and gets a row in the hub's pull-request table when it merges. The merge date is written in the tracker's time convention, converted from the UTC time GitHub reports.

## What goes where

| You have | It goes |
|---|---|
| A finished measurement | Result comment on the topic; then "Current state", "Results" and the hub's number sources if it is the new headline |
| The owner said yes, no or "do it this way" | Decision comment with their exact words; then the topic's "Decisions" table |
| A crash, a dead end, a rejected idea | Failure comment; then "Negative results and limitations" |
| A plan for the next hours | A new resume comment on the hub and, if work is in flight, a checkpoint comment |
| A doubt about an earlier number | Correction comment once checked; until then an item under "Not established" or "Open work" |
| A file path that matters | "Code and evidence" of the topic |
