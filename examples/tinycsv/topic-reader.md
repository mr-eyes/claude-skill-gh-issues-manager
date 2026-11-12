## Current state

At commit 4f2a9c1 the reader passes 41 of 53 conformance files (conformance set v2, strict quoting). The 12 failing files all contain a newline inside a quoted field. Mixed line endings are handled: 6 of 6 files pass.

As of 2026-03-04 16:30 PST. Feeds: release notes 0.3.0, fixed. Hub: NEW-hub.

## Methods and settings

The reader is a hand-written state machine in `tinycsv/reader.py`. Conformance is measured by `tests/conformance/run.py`, which parses each file and compares the rows with the expected JSON beside it. Strict quoting means a quote character inside an unquoted field is an error.

## Results

| Measure | Value | Denominator | Run or version | Source path |
|---|---|---|---|---|
| Conformance files passing | 41 | 53 | commit 4f2a9c1 | `tests/conformance/report-4f2a9c1.txt` |
| Files with mixed line endings passing | 6 | 6 | commit 4f2a9c1 | `tests/conformance/report-4f2a9c1.txt` |
| Files with quoted newlines passing | 0 | 12 | commit 4f2a9c1 | `tests/conformance/report-4f2a9c1.txt` |

## Decisions

| Date and time | Decided by | Exact words | Where recorded |
|---|---|---|---|
| 2026-03-04 15:55 PST | Sam Rivera | "Make strict the default. People who want the sloppy mode can ask for it." | Decision comment of 2026-03-04 on this issue |

## Negative results and limitations

Splitting on line endings before parsing was tried first and dropped: it cannot represent a newline inside a quoted field, which is why 12 files fail.

## Not established

Behavior on files larger than memory has not been tested. Encodings other than UTF-8 have not been tested; that is untested, not known to fail.

## Open work

| Item | Next step | Owner |
|---|---|---|
| Newlines inside quoted fields | Finish the task in NEW-task-newlines | Claude session |

## Code and evidence

| Kind | Reference | What it is |
|---|---|---|
| Commit | 4f2a9c1 | Reader with strict quoting |
| Path | `tests/conformance/report-4f2a9c1.txt` | Conformance report the numbers come from |

## Provenance

Dated comments on this issue. Conformance set v2 is described in `tests/conformance/README.md`.

## Related topics

NEW-speed measures the read time of the same commit.
