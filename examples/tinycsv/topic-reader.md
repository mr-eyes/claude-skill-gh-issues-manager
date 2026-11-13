# Reader: quoted fields and line endings

This body is the release-notes text for the sections below: the current version only, ready to copy. The comments on this issue are its history (dated results, decisions, failures and corrections) and are never release-notes text.

## Changed

- Strict quoting is the default: a quote character inside an unquoted field is an error, so a malformed file fails instead of loading wrong rows. Pass `strict=False` for the lenient mode.

## Fixed

- Quoted fields are read correctly, with the one exception listed under known issues. 41 of the 53 files of the conformance set pass.
- Files with mixed line endings are read correctly: 6 of 6 such files in the conformance set pass.

### Table: conformance - Conformance files passing, by kind of file

Files of the conformance set that the reader parses to the expected rows, by the feature they test.

| Kind of file | Passing | Files |
|---|---|---|
| Mixed line endings | 6 | 6 |
| Newline inside a quoted field | 0 | 12 |
| All other files | 35 | 35 |
| All files | 41 | 53 |

## Known issues

- A newline inside a quoted field is not supported. Each of the 12 conformance files that fail, of 53, contains one.
- Files larger than memory and encodings other than UTF-8 have not been tested; they are untested, not known to fail.

## Sources

| Statement or number | Source |
|---|---|
| 41 of 53 files pass; 12 fail, each with a newline inside a quoted field | `tests/conformance/report-4f2a9c1.txt`, conformance set v2, commit 4f2a9c1 |
| 6 of 6 files with mixed line endings pass | `tests/conformance/report-4f2a9c1.txt`, commit 4f2a9c1 |
| Strict quoting as the default | `tinycsv/reader.py`, commit 4f2a9c1 |
| Table conformance | data `tests/conformance/report-4f2a9c1.txt`; command `python tests/conformance/run.py --summary`; commit 4f2a9c1 |
