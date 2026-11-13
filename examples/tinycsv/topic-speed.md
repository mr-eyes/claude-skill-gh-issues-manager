# Read speed against the standard library

This body is the benchmark-note text for the sections below: the current version only, ready to copy. The comments on this issue are its history (dated results, decisions, failures and corrections) and are never benchmark-note text.

## Methods

Read speed was measured on three files of 1 MB, 10 MB and 100 MB. Each file was read 5 times by tinycsv and 5 times by the standard library's `csv` module, each read in a fresh process so that no read reuses the work of an earlier one, and the median wall time is reported. All reads ran on one laptop with Python 3.12 and one thread.

## Results

tinycsv read the 100 MB file in a median of 1.84 s over 5 runs, against 1.21 s for the standard library. tinycsv was slower on 3 of 3 files.

## Limitations

The measurements come from one machine and one Python version. Memory use was not measured. The reader measured does not support newlines inside quoted fields, so files that contain them are not represented.

## Sources

| Statement or number | Source |
|---|---|
| Medians of 1.84 s and 1.21 s over 5 runs; slower on 3 of 3 files | `bench/out/run-0304/summary.tsv`, commit 4f2a9c1 |
| Benchmark files | bench data v1 under `bench/data/` |
| Timing method | `bench/run.py`, commit 4f2a9c1 |
