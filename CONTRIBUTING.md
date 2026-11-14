# Contributing

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests run the scripts against `tests/fake_gh.py`, a local stand-in for `gh` selected with the `RECORTEX_GH` environment variable. They work in temporary folders under `.tmp/` and remove them afterwards; set `RECORTEX_TEST_KEEP=1` to keep them for inspection. No test may contact GitHub.

The suite passes on Python 3.14 on Linux. The lock race test starts its workers with the `fork` start method and is skipped where that method does not exist.

Check the packaging with `claude plugin validate .`.

## Rules for changes

- Scripts use bash, the Python 3 standard library and the `gh` CLI, nothing else.
- A script that writes to GitHub has a `--dry-run` that prints the exact commands. A dry run of `create_issues.py` makes no network call.
- No script deletes issues, comments or labels, or edits a posted comment. The only labels a script changes on an existing issue are section labels that follow its body's headings.
- A new lint rule comes with a test that shows it firing and a test that shows it staying quiet.
- A change to a template's sections is also a change to `KINDS` in `lint_drafts.py`, to `references/issue-model.md` and to the example drafts.
- A topic body is deliverable text: a change to the final-record template or to a profile's section labels keeps the headings in `profiles/*.json`, the label descriptions and `references/profiles.md` in step.
- A GraphQL query uses only fields listed in `tests/fixtures/github-schema-excerpt.graphql`, which is copied from GitHub's public schema. Add the field's signature there, unchanged, when a query needs a new one; `tests/fake_gh.py` rejects anything else, as GitHub would.
- The resume block is an append-only comment on the hub; no script edits one, and an edited one is never shown. Text printed by the hook stays inside its data frame, includes an issue title only when the issue was opened by an allowed account and never renamed by another, and is printed only for repositories the user trusted.
- The index and the hook state are never written in the project tree, and every entry point (hooks, the session's Bash tool, a user's shell) resolves the same folders: `$XDG_CACHE_HOME` and `$XDG_STATE_HOME`. Do not read `CLAUDE_PLUGIN_DATA`, which Claude Code sets only for hooks. Tests may set `RECORTEX_DATA_HOME` together with `RECORTEX_TESTING=1` to put the index and the state in one sandbox folder (`$RECORTEX_DATA_HOME/recortex`); nothing else uses them. Folders from the environment (`XDG_*`, `RECORTEX_TRUSTED_FILE`) are used only when they are absolute paths. Storage goes through `storage.py`: everything in a `private/` folder with mode 0700 inside the top folder, files written through a temporary file with mode 0600, no symlinks followed, and an index read only when it carries the plugin's mark for this user. A lock of another process is judged and removed only by the process that holds its claim, `sync.lock.claim`, the hard link that only one process can make at a time; the claim gets a new time stamp at once, the lock is read through its path, and that descriptor stays open until the lock is removed; no lock is renamed away. In a project that is set up and trusted, a hook that cannot show the brief says so in one line instead of staying silent. Text from GitHub or from the project reaches a hook payload only inside the data frame and through `brief.defuse()`; outside it, only the plugin's own text, numbers and values checked against a strict pattern.
- A pattern that checks an untrusted name, number or time uses explicit ASCII classes (`[0-9]`, `[A-Za-z0-9]`, not `\d`, `\w` or `\s`) and `fullmatch`, or `re.ASCII` where a class must stay as it is. The scripts write `[0-9]` and never `\d`, in every pattern; a test checks it. A repository name goes through `recortex.valid_repo`, GitHub's form of `owner/name`.
- The agents in `agents/` never post to GitHub and never start another agent. The drafter's tools are file tools only. The reviewer and the auditor are read-only by instruction: they have Bash for read commands, so do not describe them as unable to write. New hook text is fixed wording plus validated numbers or names, or sits inside the data frame.
- `SKILL.md` stays short. Detail goes into `references/`, and every reference file is linked from `SKILL.md`.
- Names live in `names.py`: the plugin's name, the configuration file, the folder, the variable prefix and the workflow, current and from before the rename (`gh-issues-manager`, `.gh-issues-manager.json`, `GHIM_`, `ghim-triage.yml`). Plugin variables are read only through `names.env`, and no other module spells an earlier name; a test scans the tree for them. An earlier name that is still read has a test for the earlier name alone, the current one alone, and both. `renames` in `.claude-plugin/marketplace.json` is append-only history. The `ghim:` markers are the record format and are not renamed. The shared module is `recortex.py`, and the tests also honor `GHIM_TEST_KEEP`.
- Examples use invented projects only.

## Releases

`version` in `.claude-plugin/plugin.json` pins installed copies to that version. Raise it with every change that users should receive.
