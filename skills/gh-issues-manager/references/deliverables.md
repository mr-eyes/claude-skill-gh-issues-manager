# Preparing the deliverable

The record is organized so that writing the paper, release notes or report is assembly, not archaeology. The bodies of the issues with a section label are the deliverable's text; assembly reads bodies only. Comments are history and are never copied into the deliverable.

## Before assembling

1. Read the hub in full. Check that the newest resume comment is recent and that no issue labeled `needs-decision` or `active` is open for a section you are about to assemble with a result it would change.
2. For each body, read the newest result, decision and correction comments of its issue. If one changes what the deliverable says and the body does not say it, the body is stale: edit it first (SKILL.md, "Change the deliverable text"), then assemble.
3. Do one consistency pass over all bodies together: the same quantity has the same value, denominator and source everywhere; one term is used for one thing; every `#N` pointer supports what cites it; no two bodies contradict each other.

## Assembling

For each section, in the order of the hub's deliverable table, take from every listed issue the text under that section's `## ` heading, and nothing else. The "Sources" sections give the file, table, commit or tag behind each number; use them to build figure and table inputs, the data and code availability statement, and the reference list of resources, not as text.

When the deliverable needs something no body says, that is a finding about the record. Record it properly first (a result comment, then the body), or open an `active` issue for it, instead of filling the gap from memory or from a comment.

Do not copy text from comments, from the former bodies kept as "Record: former issue body" comments, or from older trackers. They are history.

## Per profile

- **Manuscript.** One pass per section label, in order: `ms:background`, `ms:methods`, `ms:results`, `ms:limitations`, `ms:supplement`. Keep a table in the hub mapping each figure and table to its topic. Record submission, reviews and responses as events on a "Submission" topic; quote reviewer comments exactly.
- **Software.** Group the release notes by `rel:` label and take each line from the matching section of the topic bodies. Known issues come from the "Known issues" sections. The hub's pull-request table lists what merged since the last tag, to check that every merged change is covered by a body.
- **Research report.** Follow the `rd:` labels in order; the report's recommended next work is the union of the "Recommendations" sections. Open work that is not a recommendation stays in `active` issues.
- **Prototype recommendation.** The "Recommendation" sections state the go or no-go with the acceptance criterion as decided, "Measurements" the evidence against it, and "Limitations" what was not tried.

## After the deliverable ships

Post a result comment on the hub naming the version that shipped (tag, DOI, submission identifier) and the commit of every input, post a new resume block, and take a snapshot so the state at release is kept offline as well.
