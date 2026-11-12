### Result: 2026-03-04 14:10 PST - first speed benchmark

**What ran:** `python bench/run.py --repeat 5` at commit 4f2a9c1, output in `bench/out/run-0304/`.

**Configuration:** bench data v1 (1 MB, 10 MB, 100 MB), Python 3.12, one thread, one laptop.

**Numbers:**

| Measure | Value | Denominator | Source path |
|---|---|---|---|
| Median read time, 100 MB, tinycsv | 1.84 s | 5 runs | `bench/out/run-0304/summary.tsv` |
| Median read time, 100 MB, standard library | 1.21 s | 5 runs | `bench/out/run-0304/summary.tsv` |
| Files where tinycsv is slower | 3 | 3 | `bench/out/run-0304/summary.tsv` |

**Exclusions and failures:** None. All 30 timed reads finished.

**Cost:** About 4 minutes of laptop time.

**Not established:** Memory use. Speed on other machines or Python versions.

**Next step:** Rerun after the quoted-newline change, owner Claude session
