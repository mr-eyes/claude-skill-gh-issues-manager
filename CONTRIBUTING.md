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
- No script deletes issues, comments or labels, or edits a posted comment.
- A new lint rule comes with a test that shows it firing and a test that shows it staying quiet.
- A change to a template's sections is also a change to `KINDS` in `lint_drafts.py`, to `references/issue-model.md` and to the example drafts.
- `SKILL.md` stays short. Detail goes into `references/`, and every reference file is linked from `SKILL.md`.
- Examples use invented projects only.

## Releases

`version` in `.claude-plugin/plugin.json` pins installed copies to that version. Raise it with every change that users should receive.
