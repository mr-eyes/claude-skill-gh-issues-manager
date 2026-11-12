# Preparing the deliverable

The record is organized so that writing the paper, release notes or report is assembly, not archaeology.

## Before writing

1. Read the hub in full. Check that the newest resume comment is recent and that no issue labeled `needs-decision` is open for a section you are about to write.
2. For the section at hand, open its table under "Deliverable sections" and read every listed final record from top to bottom.
3. For each record, read the newest comments after the "As of" date in "Current state". If a result, decision or correction is newer than the current state, the record is stale: update it first (SKILL.md, "Change a conclusion"), then write.

## While writing

| Take | From |
|---|---|
| Claims | "Current state" and "Results" of the final record; never from a comment that the body has not absorbed |
| Headline numbers | The hub's number-sources table; check that numbers used together share data version, code version and configuration |
| Methods text | "Methods and settings" |
| Limitations | "Negative results and limitations" and "Not established"; both belong in the deliverable, not only the successes |
| Reasons for choices | "Decisions", with the exact words available if a co-author or reviewer asks |
| Figure and table inputs | "Code and evidence" |

Do not use folded "Replaced on" blocks as sources; they are history.

When the deliverable needs something the record lacks, that is a finding about the record. Add it under "Open work" of the topic, or record it properly first, instead of filling the gap from memory.

## Per profile

- **Manuscript.** One pass per section label (`ms:background` to `ms:supplement`). Keep a table in the hub mapping each figure and table to its topic. Record submission, reviews and responses as events on a "Submission" topic; quote reviewer comments exactly.
- **Software.** List closed pull requests since the last tag from the hub's table, group by `rel:` label, and write each release-note line from the topic's current state. Known issues come from "Not established" and "Negative results and limitations".
- **Research report.** Follow the `rd:` labels in order; the report's "next work" section is the union of the topics' "Open work" tables.
- **Prototype recommendation.** State the acceptance criterion as decided, the measurements against it, and what was not tried.

## After the deliverable ships

Post a result comment on the hub naming the version that shipped (tag, DOI, submission identifier) and the commit of every input, post a new resume block, and take a snapshot so the state at release is kept offline as well.
