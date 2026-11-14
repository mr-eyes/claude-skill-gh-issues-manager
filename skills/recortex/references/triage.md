# Triage of issues opened by hand

People open issues by hand: a bug, a question, a task, a documentation fix, an idea, a data problem. None of them fits the record until it is triaged.

## Detection

An open issue needs triage when it carries the `triage` label, or when it has no role label (`hub`, `final-record`, `active`), no closed-out type (`type:duplicate`, `type:out-of-scope`) and no triage comment yet from an allowed account. A triaged issue may stay open without a role label, for example a question waiting for its answer; it is listed again only when someone adds the `triage` label. `index.py query triage` lists them, the SessionStart brief adds one line, "N issues need triage: #a, #b", and the `record-auditor` agent reports them. Issues created by the skill's scripts always carry a role label.

The optional workflow `.github/workflows/recortex-triage.yml` (from `templates/recortex-triage.yml`, written by `setup.py apply` when the user asks) adds the `triage` label to any issue opened without a role label, so the flag appears even when no session runs. It uses only the default `GITHUB_TOKEN` with permission to write issues, reads no title or body, and never edits one. A workflow acts only on the repository it is committed to: for a record kept in another repository, commit it there.

## Classification

Every project has the core types `type:task`, `type:bug`, `type:question`, `type:docs`, `type:idea`, `type:data`, `type:decision-needed`, `type:duplicate` and `type:out-of-scope`; profiles add their own, for example `type:reviewer-comment` (manuscript, proposal), `type:release` (software) or `type:supervisor-comment` (thesis).

For each issue, post a comment from `templates/comment-triage.md` (kind `triage`): the marker and the heading `### Triage: <date time zone> - <type>`, who opened it, their words quoted exactly, the type, the route, a one-line reason, and what waits for the user's confirmation. Then apply the type label and remove `triage`. Quote the person who opened the issue; never paraphrase their request into a stronger claim.

## Routes

| Type | Route |
|---|---|
| `type:task`, `type:bug` | Becomes an `active` issue (this one, relabeled, or a new one) that names its destination topic |
| `type:question` | Answered from the record in a comment, or added to the owner's decisions issue when only the owner can answer |
| `type:docs` | A body edit on its topic, or a change in the repository, with the issue linked |
| `type:idea` | Kept open and labeled `active` with its type, or added to the decisions issue |
| `type:duplicate` | Linked to the original |
| `type:out-of-scope` | Explained in the comment |

Labeling and commenting need no confirmation. Closing an issue, changing the project's scope, and editing a deliverable body each need the user's yes first; the triage comment says which of these it waits for. Triage comments are events: the timeline and `compile.py` include them.
