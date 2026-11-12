# Bootstrapping a new project

Paths below are relative to the skill folder. The scripts read `.gh-issues-manager.json` from the project root only (`CLAUDE_PROJECT_DIR`, else the top of the git checkout, else the current folder).

## 1. Agree on the frame with the owner

Ask once, together, and record the answers (they become the first decision comment on the hub):

| Question | Becomes |
|---|---|
| Which repository holds the issues? | `repo` |
| What is the deliverable, and what are its sections? | The profiles and the hub's deliverable tables |
| What are the first topics? | `topics`, one final record each |
| Which time zone do we write times in? | `timezone` and the hub's convention line |
| Is any data restricted (identifiers, unpublished names, credentials)? | `restricted_patterns` and recording rule 9 |
| Who decides what? | The "Decided by" values to expect |

Check that `gh auth status` works and that the account may create issues and labels in the repository.

## 2. Write the configuration

Copy `templates/gh-issues-manager.example.json` to `.gh-issues-manager.json` at the project root and fill it in. Leave `hub` out until the hub exists. The file holds no secrets and can be committed.

## 3. Create the labels

```bash
python3 scripts/setup_labels.py --dry-run
python3 scripts/setup_labels.py
```

The dry run without `--existing` does not read the repository and lists every label as a creation. The real run reads the existing labels first, creates only the missing ones and leaves differing ones alone unless `--update` is given.

## 4. Draft the first issues

Create a drafts folder that holds nothing but drafts (for example `.tmp/drafts/bootstrap/`, kept out of version control). From the templates write:

- `hub.md` from `templates/hub.md`
- one `topic-<name>.md` per topic from `templates/final-record.md`
- optionally the first active task from `templates/active-task.md`

Use `NEW-<key>` wherever an issue number belongs. A new topic's record may be thin; write what is known, and put the rest under "Not established" and "Open work" instead of leaving sections empty.

List the drafts in `manifest.json` (see `templates/manifest.example.json`): for each issue a `key`, `kind`, `title`, `labels` and `body_file`; `"pin": true` for the hub.

## 5. Lint, dry-run, create

```bash
python3 scripts/lint_drafts.py --manifest .tmp/drafts/bootstrap/manifest.json
python3 scripts/create_issues.py --manifest .tmp/drafts/bootstrap/manifest.json --dry-run
python3 scripts/create_issues.py --manifest .tmp/drafts/bootstrap/manifest.json
```

The last command creates the issues, replaces every placeholder, pins the hub, reads each body back from the API and prints the key-to-number table. If it stops midway (network, rate limit), run the same command again: finished items are skipped, because progress is kept in `manifest.json.state.json`.

An issue whose draft contains placeholders is created with a one-line stub body and receives its full text seconds later, once all numbers are known.

## 6. Finish

1. Put the hub number into `.gh-issues-manager.json` as `hub`.
2. Run `python3 scripts/resume_block.py show --active` to confirm the block reads back.
3. Post the frame agreed in step 1 as a decision comment on the hub, with the owner's exact words.
4. Offer the CLAUDE.md snippet and the SessionStart hook (see [session-protocol.md](session-protocol.md)). The hook prints nothing until the user adds the repository to their own trusted list; give them the line to add.
5. Take a first snapshot if offline reading matters.

## Adding to an existing repository

The same steps work in a repository that already has issues. Existing issues are not touched. If they hold project history, treat them as an older tracker in the same repository and follow [migration.md](migration.md); pointer comments then use plain `#N`.
