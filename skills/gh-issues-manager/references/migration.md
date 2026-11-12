# Migrating from an older tracker

The goal is that the new tracker can be read without the old one. The old tracker stays exactly as it is, as provenance.

## Rules

- Never delete, edit, close, relabel or lock anything in the old tracker.
- Copy content, do not link to it as a substitute. A new final record that says "see old issue 14" is not self-contained.
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
| A long issue about one subject | The base of one final record |
| Several issues about one subject | One final record that merges them |
| An issue that mixes subjects | Parts of several final records |
| A decision buried in a thread | A row in "Decisions" with the exact words, date and a link to the old comment |
| An abandoned idea | "Negative results and limitations" of the topic |
| A pull request | A row in the hub's pull-request table and in the topic's "Code and evidence" |
| Noise (duplicates, test issues) | "Not carried over" with the reason |

Show the map to the owner before writing records. Topic boundaries are a judgment call and cheap to change now.

### 3. Write the new records

For each topic, write a final record from the template using the mapped items. While copying:

- Rewrite every reference. A bare `#14` copied from the old tracker would link to issue 14 of the new repository, which is a different thing. Write `owner/old-tracker#14` or the full URL. The linter flags bare references that do not exist in the target repository, but one that happens to exist there passes, so check each by eye.
- Keep dates in their original form and convert times to the new tracker's convention, noting the conversion if the day changes.
- Keep quotes exact and attribute them with a link to the old comment.
- When old items contradict each other, do not pick silently. State the current conclusion, keep the older one in a folded block, and if it cannot be settled, list it under "Not established".
- Check numbers against artifacts where the artifacts still exist. Where they do not, say so: "as reported in owner/old-tracker#14; source file no longer available".
- Fill "Provenance" with every old item the record draws on.

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
- Every new record passes the "readable alone" test.
- A reader given only the new hub can answer: what is the current state of each topic, where does each headline number come from, what was decided and by whom.
- Take a snapshot of the new tracker and search it for the old repository's bare issue numbers.
