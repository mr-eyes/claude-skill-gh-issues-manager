# Contributing

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests run the scripts against `tests/fake_gh.py`, a local stand-in for `gh` selected with the `GHIM_GH` environment variable. They work in temporary folders under `.tmp/` and remove them afterwards; set `GHIM_TEST_KEEP=1` to keep them for inspection. No test may contact GitHub.

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
- The index and the hook state are never written in the project tree. Storage goes through `storage.py`: everything in a `private/` folder with mode 0700 inside the top folder, files written through a temporary file with mode 0600, no symlinks followed, and an index read only when it carries the plugin's mark for this user. In a project that is set up and trusted, a hook that cannot show the brief says so in one line instead of staying silent. Text from GitHub or from the project reaches a hook payload only inside the data frame and through `brief.defuse()`; outside it, only the plugin's own text, numbers and values checked against a strict pattern.
- The agents in `agents/` never post to GitHub and never start another agent; the drafter may only read and write files, the reviewer and the auditor only read. New hook text is fixed wording plus validated numbers or names, or sits inside the data frame.
- `SKILL.md` stays short. Detail goes into `references/`, and every reference file is linked from `SKILL.md`.
- Examples use invented projects only.

## Releases

`version` in `.claude-plugin/plugin.json` pins installed copies to that version. Raise it with every change that users should receive.
