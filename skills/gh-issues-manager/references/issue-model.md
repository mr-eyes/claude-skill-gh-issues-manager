# The issue model

One model serves every project type. Profiles (see [profiles.md](profiles.md)) only change the label set, the section headings and what counts as an event.

The model rests on one split. The body of a topic issue that carries a deliverable-section label is the text for that section of the deliverable: the current version only, in the deliverable's voice, ready to copy. The comments are the history. Whoever assembles the deliverable reads bodies only; whoever wants to know how the text came to be reads comments.

## Contents

- The hub
- Final-record issues
- Events
- Changing the deliverable text
- Active tasks
- Labels
- Pull requests
- What goes where

## The hub

One issue, pinned, label `hub`. It is the single entry point: a reader who knows nothing opens the hub and can reach everything else. Template: `templates/hub.md`. Its sections, in order:

| Section | Holds |
|---|---|
| Deliverable text | The rule that bodies with a section label are deliverable text and comments are history |
| Resume here | A fixed note saying that the current resume block is the newest "Resume block" comment on the hub |
| Project | A short statement of the project and the tracker's time convention |
| Map | A Mermaid flowchart: deliverable sections, the topic issues that feed them, the pull requests behind the topics |
| Deliverable sections | One table per deliverable listing, section by section in the deliverable's order, the issues whose bodies hold its text |
| Active issues | The open `active` issues, each with its destination topic |
| Pull requests | Each pull request, when it merged, what it changed, its topic |
| Labels | The label legend |
| Older tracker | One row per item of an older tracker and its new home, or "None" |
| Recording rules | The rules for recording new work |

The resume block itself is not in the body. It is a comment on the hub, posted anew at the end of every working stretch from `templates/resume-block.md`: last updated, current focus, active issues, last decisions, next actions with owners, holds. Comments have one author each and are never edited here, which is what lets the hook check who wrote the block before showing it (see [session-protocol.md](session-protocol.md)).

The hub holds pointers, not content. It repeats no number from a body: a number stated in two places drifts, so each number lives in one body, next to its source. The hub is edited in place when the list of issues per section or the list of active issues changes.

Numbers from different runs must never be combined. Each body's "Sources" section names the file, table, commit or tag behind each number, and before a deliverable is assembled one consistency pass over all bodies checks that the same quantity has the same value, denominator and source everywhere.

## Final-record issues

One issue per topic, label `final-record` plus section and topic labels. A topic is a unit that the deliverable will describe: a method, an analysis, a component, a figure, a claim. Template: `templates/final-record.md`. The body holds, in this order:

| Part | Holds |
|---|---|
| Title line | `# ` and the topic as the deliverable names it |
| Role sentence | One sentence: this body is deliverable text, current version only; the comments are history |
| One `## ` section per deliverable section | The text for that section, under the heading the profile defines (for example `## Methods` for `ms:methods`). The issue carries exactly the section labels of these headings |
| Sources | The file, table, commit or tag behind each number and claim. Commits and tags appear only here; resource releases, such as a reference build or a database release, may be named here |

What the text may and may not hold:

| Allowed | Not allowed |
|---|---|
| The current statement, in the deliverable's voice | Dates, "As of" lines, version history or version labels of the work itself |
| Every number with its denominator | Folded "Replaced on" blocks or any other old text |
| A design choice with a one-sentence reason | Decision tables or the story of a decision |
| A limitation stated as a property of the final method or result | The story of a failed attempt |
| Sub-headings (`###`) inside a section, not named like a section heading | Open work, next steps, provenance, links to older trackers, job identifiers |
| A figure block: `### Figure: <id> - <title>`, a caption, and the image embedded from a committed path at a commit or tag (`![text](https://github.com/<owner>/<repo>/blob/<commit or tag>/<path>?raw=true)`), with a Sources row `Figure <id>` naming the data file and the exact command | An image linked from a branch, which can change under the text |
| A table block: `### Table: <id> - <title>`, a caption, and a Markdown table or a link to a committed file, with a Sources row `Table <id>` | A table whose numbers have no source |

The linter enforces what it can see: no "As of" line followed by a date, month or year, no date and time in the text, no `<details>` block, no heading for decisions, open work, provenance, next steps or the other sections of the older record form, no dated heading outside "Sources", "Sources" last, no line that looks like a section heading but is not one, and section headings that agree with the issue's labels. It cannot see a job identifier, a missing denominator or a commit outside "Sources"; review catches those.

In a project whose profiles define no section labels, the body is still the current text of the topic and nothing else, under plain `## ` headings of your choice, followed by "Sources".

The test for a body: someone who has read nothing else can paste it into the deliverable, and it is right. If the text says "as discussed", "see chat" or "as of", it fails the test.

A body is at most 65,536 characters. A deliverable section that needs more is split into two topics.

## Events

An event is something that happened and will matter later. Each one becomes a dated comment on its topic issue, never a new top-level issue and never text in a body. Five kinds, each with a template:

| Kind | When | Template |
|---|---|---|
| Result | An experiment, analysis, benchmark or test campaign finished | `templates/comment-result.md` |
| Decision | Someone with authority chose something | `templates/comment-decision.md` |
| Failure | A run, approach or change failed | `templates/comment-failure.md` |
| Checkpoint | A working stretch ends with work in flight | `templates/comment-checkpoint.md` |
| Correction | A posted statement or number was wrong | `templates/comment-correction.md` |
| Triage | An issue opened by hand was given a type and a route | `templates/comment-triage.md` |

Every event comment starts with a machine-readable marker line, then its heading:

```
<!-- ghim:event type=result at=2026-03-04T14:10-08:00 -->
### Result: 2026-03-04 14:10 PST - first speed benchmark
```

The heading keeps the comment list of an issue readable as a timeline; the marker gives the type and the time with its offset, so the index and `compile.py` can order every event of the project exactly. Both carry the same local date and time, and the linter checks that they agree. The comment that keeps a former body during a conversion carries `type=record`. Resume comments keep their own heading first and have no marker, because the trust check reads that heading. A merged change is recorded as a result comment whose "What ran" names the pull request and commit.

Comments are append-only. They are the history: results, decisions with the decider's exact words, failures, corrections. The decision record lives only in decision comments. Nobody rewrites them, and none of them is deliverable text.

## Changing the deliverable text

The body always says what the deliverable says now. When that changes:

1. Edit the body in place. The new text replaces the old; nothing old is folded or kept below it.
2. A result that leaves the deliverable is deleted from the body. When a section has no text left, delete its heading; its section label comes off. When a whole topic leaves the deliverable, replace its body with one line saying that the topic is not part of the deliverable and why, pointing to the dated comment that records the reason (`post_verified.py body --issue N --kind generic --body-file <line> --backup <file>`, since a final record needs a section), remove its section labels and `final-record` with `gh issue edit N --remove-label <label>`, remove its rows from the hub, and close it as not planned (`gh issue close N --reason "not planned"`), or label it `active` if work on it continues.
3. Post the result, decision or correction comment that caused the change. The comment explains why; the body shows what is true now. GitHub keeps every earlier version of the body in the issue's edit history.
4. Update the hub only if the list of issues per section changed.

`post_verified.py body --kind final-record` replaces the body and moves the section labels to follow the headings in one run. It refuses an issue labeled `hub` or `active` or without `final-record`, and an issue that carries section labels of profiles not in use (pass `--profile`, or `--allow-other-profiles` to leave those labels alone). It removes a section label only with `--allow-label-removal`, after printing `removes: <labels>`: a heading mistyped as `### Results` or `##Results` would otherwise drop a section silently, and the linter reports such near-headings as errors. When no profile defines section labels it changes no label and says so.

## Active tasks

Work in development (an investigation, a refactor, a rerun, a method not yet merged) gets its own issue with label `active`, and so do open questions: one issue per bounded task, or one decision list for the owner. Template: `templates/active-task.md`. It must name its destination topic and never carries a section label. Checkpoint comments go on the task while it runs. When it ends:

1. Post the outcome as a result (or failure) comment on the destination topic. If the outcome was adopted into the product (merged, integrated, released), edit the destination body to say what the deliverable now says; until then it stays out of the body.
2. Write the outcome and the link to that comment into the task's "Result" section.
3. Close the task. The `active` label stays, so closed tasks remain findable; "open and labeled `active`" is the list of work in flight.
4. Post a new resume block.

A task that ends with nothing to report still gets a result: "no change, because ...".

## Labels

| Group | Labels | Use |
|---|---|---|
| Role | `hub`, `final-record`, `active`, `triage`, `needs-decision`, `migrated` | What kind of issue this is; `triage` marks an issue opened by hand that is not yet placed |
| Type | `type:task`, `type:bug`, `type:question`, `type:docs`, `type:idea`, `type:data`, `type:decision-needed`, `type:duplicate`, `type:out-of-scope`, plus the profile's own | What an issue opened by hand is (see [triage.md](triage.md)) |
| Deliverable section | From the profile, for example `ms:methods` or `rel:fixed` | Which part of the deliverable the issue's body is the text of; follows the body's `## ` headings |
| Topic | `topic:<name>` | Which topic the issue or pull request belongs to |

Every issue and pull request gets its labels when it is opened. An unlabeled item is invisible to the queries the session protocol runs.

## Pull requests

Every pull request names its topic issue in its description ("Topic: #12"), carries the topic label, and gets a row in the hub's pull-request table when it merges. The merge date is written in the tracker's time convention, converted from the UTC time GitHub reports.

## What goes where

| You have | It goes |
|---|---|
| A finished measurement | Result comment on the topic; then the body, with its source under "Sources", if the deliverable now says something new |
| The owner said yes, no or "do it this way" | Decision comment with their exact words; in the body only what the deliverable now says, with a one-sentence reason |
| A crash, a dead end, a rejected idea | Failure comment; in the body only a limitation of the final method or result that follows from it |
| Work in development or an open question | An `active` issue that names its destination topic |
| A plan for the next hours | A new resume comment on the hub and, if work is in flight, a checkpoint comment |
| A doubt about an earlier number | An `active` issue until checked; then a correction comment, and the body edited if the number was wrong |
| A file, table, commit or tag behind a number | "Sources" of the body |
| A job identifier, log path or older-tracker link | The comment that reports the event |
