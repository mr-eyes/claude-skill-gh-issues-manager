## Current state

At commit 4f2a9c1, tinycsv reads the 100 MB benchmark file in a median of 1.84 s over 5 runs, against 1.21 s for the standard library on the same machine. tinycsv is slower on all 3 of 3 benchmark files.

As of 2026-03-04 14:10 PST. Feeds: benchmark note, results. Hub: #1.

<details>
<summary>Replaced on 2026-03-04 14:10 PST: the first run used 3 repeats; rerun with 5</summary>

At commit 4f2a9c1, tinycsv reads the 100 MB benchmark file in a median of 1.79 s over 3 runs.

</details>

## Methods and settings

`bench/run.py` reads each file 5 times in a fresh process and reports the median wall time. Python 3.12, one thread, bench data v1 (three files: 1 MB, 10 MB, 100 MB).

## Results

| Measure | Value | Denominator | Run or version | Source path |
|---|---|---|---|---|
| Median read time, 100 MB, tinycsv | 1.84 s | 5 runs | run-0304, commit 4f2a9c1 | `bench/out/run-0304/summary.tsv` |
| Median read time, 100 MB, standard library | 1.21 s | 5 runs | run-0304 | `bench/out/run-0304/summary.tsv` |
| Files where tinycsv is slower | 3 | 3 | run-0304 | `bench/out/run-0304/summary.tsv` |

## Decisions

None so far.

## Negative results and limitations

tinycsv is slower than the standard library on every file measured. One machine, one Python version.

## Not established

Memory use was not measured. Speed after the quoted-newline change is not known; the numbers above are for commit 4f2a9c1 only.

## Open work

| Item | Next step | Owner |
|---|---|---|
| Rerun after the reader change | Run `bench/run.py` on the new commit | Claude session |

## Code and evidence

| Kind | Reference | What it is |
|---|---|---|
| Path | `bench/out/run-0304/summary.tsv` | Medians per file and reader |

## Provenance

Result comment of 2026-03-04 on this issue.

## Related topics

#2 holds the correctness results for the same commit.
