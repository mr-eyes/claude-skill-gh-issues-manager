# Migrating from an older tracker

> Commands on this page write `scripts/<name>` for short. That is the `scripts` folder of this skill, next to `SKILL.md`; call it by its full path.

The goal is that the new tracker can be read without the old one. The old tracker stays exactly as it is, as provenance.

## Rules

- Never delete, edit, close, relabel or lock anything in the old tracker.
- Copy content, do not link to it as a substitute. The deliverable text goes into the new bodies; the history (results, decisions, failures, with links to the old items) goes into dated comments on the new issues. A new issue that says "see old issue 14" is not self-contained.
- Every old issue and pull request is accounted for, including the ones that are not carried over.
- At most one short pointer comment per old item, and only if the owner wants pointers at all.

## Steps

### 1. Snapshot the old tracker

```bash
python3 scripts/snapshot.py --repo owner/old-tracker --out .tmp/old-tracker
```

`INDEX.md` lists every issue and pull request with state, labels and comment counts; each item's file holds its body and all comments. Work from the snapshot: it is stable, searchable and costs no API calls. Read every item in full, including closed ones and long comment threads. Decisions and negative results tend to sit deep in threads.

### 2. Build the migration map

Fill `templates/migration-map.md`: one row per old item with what it holds, the new topic it belongs to, and how it is carried over. Count the rows against the index; the two numbers must match. Typical mappings:

| Old item | Becomes |
|---|---|
| A long issue about one subject | The base of one topic issue |
| Several issues about one subject | One topic issue that merges them |
| An issue that mixes subjects | Parts of several topic issues |
| A decision buried in a thread | A decision comment with the exact words, date and a link to the old comment; in the body only what the deliverable now says, with a one-sentence reason |
| An abandoned idea | A failure comment; in the body only a limitation of the final product that follows from it |
| Work still in development, an open question | An `active` issue |
| A pull request | A row in the hub's pull-request table, and the merge commit under "Sources" of the body it supports |
| Noise (duplicates, test issues) | "Not carried over" with the reason |

Show the map to the owner before writing records. Topic boundaries are a judgment call and cheap to change now.

### 3. Write the new records

For each topic, write the body from `templates/final-record.md` and the history as dated comments, using the mapped items. While copying:

- Rewrite every reference. A bare `#14` copied from the old tracker would link to issue 14 of the new repository, which is a different thing. Write `owner/old-tracker#14` or the full URL. The linter flags bare references that do not exist in the target repository, but one that happens to exist there passes, so check each by eye.
- Keep dates in their original form and convert times to the new tracker's convention, noting the conversion if the day changes.
- Keep quotes exact and attribute them with a link to the old comment.
- When old items contradict each other, do not pick silently. Put the current statement in the body, record the older one in a comment with its link, and if it cannot be settled, open an `active` issue for it and keep the claim out of the body.
- Check numbers against artifacts where the artifacts still exist. Where they do not, say so in the comment that carries the number: "as reported in owner/old-tracker#14; source file no longer available". Such a number enters a body only with a source.
- Link every old item the record draws on from the comments, never from the body.

Add the `migrated` label to records built mainly from old content.

### 4. Create, with the hub's map of the old tracker

Put the map into the hub's "Older tracker" section (one row per old item, new home as `NEW-<key>`), list everything in a manifest, and run `create_issues.py` as in [bootstrap.md](bootstrap.md). Use an independent reviewer on the drafts first: migration is where mixed numbers and paraphrased decisions get in.

### 5. Pointers in the old tracker (optional)

If the owner wants them, add pointer comments to the same manifest, or a second one:

```json
{"issue": 14, "repo": "owner/old-tracker", "kind": "pointer", "body_file": "pointer-14.md"}
```

Draft each from `templates/pointer-comment.md`. In a comment posted to another repository, `NEW-<key>` becomes `owner/new-repo#N` automatically. Keep pointers to one or two sentences; they are signposts, not summaries.

### 6. Verify the migration

- Rows in the map equal items in the snapshot index.
- Every new body passes the "paste it into the deliverable" test, and its history is in its comments.
- A reader given only the new hub can answer: what does each section of the deliverable say, where does each number come from (the body's "Sources"), what was decided and by whom (the decision comments).
- Take a snapshot of the new tracker and search it for the old repository's bare issue numbers.

## The batch workflow with the agents

Bulk drafting and review use the plugin's agents; the main session stays the only writer to GitHub.

1. Draft: the `record-drafter` agent takes a batch of about four issues and writes draft bodies to files only, with a notes file per batch listing what it moved out of each body and why, conflicts between sources, and owner questions.
2. Review: the `record-reviewer` agent, which has not seen the drafter's reasoning, audits the batch read-only: dropped limitations first, then statements firmer than their source, numbers and denominators, the rules of the body and the source paths. It returns findings with exact replacement text.
3. Fix: the main session applies the findings to the drafts, or records why it does not.
4. Cross-issue review: when all batches are drafted, `record-reviewer` in its cross-issue mode checks all bodies together for shared numbers, terms, `#N` pointers and contradictions.
5. Post: the main session posts each body with `convert_body.py` or `post_verified.py body`, with read-back.
6. Owner questions: collected, without duplicates, in one `active` issue, the decision list.

None of the agents starts another agent. Each preloads this skill and uses the user's default model; to give an agent another model, copy its file from the plugin's `agents/` folder into the project's `.claude/agents/` and set `model:` in its frontmatter.

## Converting record bodies into deliverable text

A tracker whose topic bodies hold a full record (a dated "Current state", folded "Replaced on" blocks, decisions, open work, provenance) is converted in place, issue by issue, so that each body becomes the text for its sections of the deliverable. Nothing is lost: the former body is kept, unchanged, as a comment on the same issue.

### Draft

1. Snapshot the tracker, and save each live body as it is now, for example `gh api repos/owner/name/issues/N --jq .body > .tmp/convert/live/topic-N.md`. That copy is what the new text is drafted from, and the conversion checks against it.
2. Draft each new body from the full record (the body and every comment), in the deliverable's voice, from `templates/final-record.md`. Keep every number with its denominator and give its source under "Sources". Keep every limitation of the final product, stated as a property of the method or result.
3. In a notes file kept outside the drafts folder, list for each draft what was moved out of the body and why, one line each: history, superseded, open work, development not yet adopted, provenance. List the questions only the owner can answer.

### Review

4. Have an independent reviewer (a fresh agent or a person who has not seen your reasoning) review each batch of drafts against the former bodies and their comments. Ask it to audit the exclusions hardest: a dropped limitation of the final product is as serious as a wrong number. Ask it also to flag every statement firmer than its source.
5. Then do one consistency pass over all new bodies together: the same quantity has the same value, denominator and version everywhere; one term is used for one thing; every `#N` pointer supports what cites it; no two bodies contradict each other.
6. Collect the owner questions, without duplicates, in one `active` issue: the decision list. Statements that wait on an answer stay out of the bodies until it comes.

### Convert

7. For each issue, run the conversion as a dry run, read the record comment, the diff and the label change it prints, then run it for real:

   ```bash
   python3 scripts/convert_body.py --issue 12 --body-file .tmp/convert/drafts/topic-12.md \
       --expected .tmp/convert/live/topic-12.md \
       --note "Replaced on 2026-03-09 11:20 PST by the methods text, when the tracker moved to deliverable bodies." --dry-run
   ```

   The script stops before writing anything if the issue is labeled `hub` or `active` or lacks `final-record`, if it carries section labels of profiles not in use (pass `--profile`, or `--allow-other-profiles`), if the live body differs from `--expected` (someone edited the issue since the copy was taken; save it again and redraft), if the draft fails lint, if a section label does not exist, or if a section label would be removed without `--allow-label-removal` (it prints `removes: <labels>` first). Otherwise it posts the former body unchanged as a comment headed "Record: former issue body, kept as history (not deliverable text)" with the note as its first sentence, reads it back, checks the live body once more, replaces the body, sets the section labels from the new headings (adding the labels of new sections, removing those of sections the body no longer has), and reads the body and the labels back. A rerun after a failure continues where it stopped: a record comment by the same account that keeps the same former body is adopted, whatever its note, and the dry run says so.

   If the live body changes after the record comment is posted, the script stops without replacing the body, and the record comment then says something that did not happen. Post a correction comment that links to it (the script prints its address), then save the live body again, redraft and rerun. GitHub has no conditional edit of an issue body, so an edit in the moment between the second check and the replacement cannot be detected; the read-back and the issue's edit history show it.

   The record comment repeats the former body, so every `@name` in it notifies that account again; the script lists them before posting. A former body too long to fit in one comment with its heading and note is kept by hand: post it in two comments headed "Record: former issue body, kept as history (not deliverable text), part 1 of 2" and "part 2 of 2" with `post_verified.py comment --kind generic`, then replace the body with `post_verified.py body`.
8. Update the hub: the deliverable-text rule at the top, the issues per section, the active issues, and no numbers from the bodies.
