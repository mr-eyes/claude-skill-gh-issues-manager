# Posting and verification

Every post goes through the same five steps. The scripts do steps 3 to 5; steps 1 and 2 are yours.

## 1. Draft to a file

Write the draft from its template into the drafts folder. One file per issue body or comment. Do not compose a body inside a shell command: quoting damages backticks, dollar signs and tables, and the text cannot be reviewed or linted.

Keep the drafts folder clean. Notes, extracted tables and other scratch files go somewhere else. Posting commands take explicit file names (`--body-file`, or the manifest), never a folder or a wildcard, so a stray file cannot be posted by accident; a clean folder also keeps a reviewer from reading the wrong file.

## 2. Check against the sources, then get an independent review

For every number in the draft, open the file named as its source and read the value there. For every quote, find the original message. For every identifier (commit, job, path), check that it exists. Memory, including a compaction summary, is not a source.

For a new final record, a changed conclusion, a hub edit, or anything the deliverable will cite, ask a reviewer that does not share your context (a fresh agent, or a person) to try to break the draft. Give it the draft and the source paths, not your reasoning. Ask it to look hardest at: numbers against sources; denominators; mixed runs; exclusions and failures; claims that go beyond the evidence; things stated as negative that were only not tested. Fix what it finds, and if the review did not return, the draft is not reviewed.

Routine result and checkpoint comments need the source check but not always the reviewer; decide by what a wrong post would cost.

## 3. Lint

```bash
python3 scripts/lint_drafts.py --kind result --repo owner/name --online draft.md
```

| Check | Level |
|---|---|
| Required sections present, in order, not empty | error |
| Event header with date, time and zone | error |
| Decision carries a quote block, or says the words are not available | error |
| `{{template fields}}` or `NEW-<key>` left in the text | error |
| Bare `#N` that does not exist in the target repository | error (`--online` or `--known-numbers`), otherwise warning |
| Body over 65,536 characters | error; warning when close |
| Mermaid: `#`, parentheses, unquoted labels, nodes undefined or unused | error |
| Hub: resume markers, resume fields, block length | error |
| Secrets (common token formats) and the project's `restricted_patterns` | error |
| The project's `banned_words` | error |

The linter does not judge content. It cannot know whether a number is right.

## 4. Post

| Task | Command |
|---|---|
| Several new issues and comments | `create_issues.py --manifest <file>` |
| One comment | `post_verified.py comment --issue N --kind <kind> --body-file <draft>` |
| Replace an issue body | `post_verified.py body --issue N --kind <kind> --body-file <draft> --backup <file>` |
| Resume block only | `resume_block.py update --file <draft>` |

Run each with `--dry-run` first; it prints the exact `gh` commands. `post_verified.py body` prints a diff against the body now on GitHub and saves that body to the backup file before editing. To edit a body, start from the current one: `gh issue view N --json body --jq .body > draft.md`, or `gh api repos/owner/name/issues/N --jq .body`.

## 5. Read back and compare

After each write the scripts fetch the stored text from the API and compare it with the draft, ignoring only line-ending style and trailing whitespace. `verified:` means equal. `MISMATCH:` shows the first differing line; the usual causes are a body changed by someone else in between, or text altered on the way in. Resolve it before going on, and do not report the post as done until it verifies.

If you ever post by hand, do the same check by hand:

```bash
gh issue comment N --body-file draft.md          # prints the comment URL, ending in the comment id
gh api repos/owner/name/issues/comments/<id> --jq .body > back.md
diff <(sed 's/[[:space:]]*$//' draft.md) <(sed 's/\r$//; s/[[:space:]]*$//' back.md)
```

## What the scripts never do

They never delete an issue, comment or label, never edit a posted comment, never close or reopen issues, and never post a file that was not named on the command line or in the manifest. Closing a finished task is a deliberate `gh issue close N` by the session or the owner.
