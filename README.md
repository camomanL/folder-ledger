# folder-ledger

A read-only Python utility for cataloging folders and finding duplicate file
contents. It never moves or deletes input files. Requires Python 3.10 or newer;
there are no runtime dependencies, accounts, services, or network requests.

## Run from this directory

```sh
python -m folder_ledger examples/documents --duplicates
python -m folder_ledger examples/documents --duplicates --output inventory.json
python -m folder_ledger examples/documents --hashes --format csv --output inventory.csv
python -m folder_ledger examples/documents --exclude 'archive' --exclude '*.tmp'
python -m unittest discover -s tests -v
```

The synthetic example has three files and one duplicate group. Outputs must
be outside the scanned directory. Existing reports are protected; use
`--force` to replace a report explicitly. `python -m folder_ledger --help`
lists the options. Running directly needs no installation. Optional editable
installation uses `python -m pip install -e .` and requires setuptools.

## Output contract

The terminal reports file/byte counts, duplicate-group count, skips and errors.
Exit codes: 0 for a complete scan; 1 for a scan with recorded errors; 2 for
invalid input or a report-write failure. An incomplete JSON report still
contains the accessible files and errors. Error details also go to stderr.

JSON schema version 1 contains `files`, `duplicates`, `skipped` and `errors`.
Each file has a slash-normalized relative `path`, byte `size`, integer
`mtime_ns` (Unix epoch nanoseconds), and nullable `sha256`. CSV contains those
four file columns, with an empty cell for uncomputed hashes; use JSON for
duplicate groups and structured errors. CSV paths are raw data; import them
as text in a spreadsheet rather than interpreting them as formulas.
For POSIX filenames containing undecodable bytes, use JSON: CSV rejects
unencodable names before creating a report, with exit code 2.

`--hashes` computes every file's SHA-256. `--duplicates` first groups by size
and hashes only candidates with matching sizes; only matching hashes form a
duplicate group. Empty files can be duplicates. Hard links appear as separate
paths. Symlinks, Windows junctions/reparse points and special files are skipped.
The input root itself must be a regular directory, not a link.

Exclusion globs use Python `fnmatchcase` against the entire relative path:
case-sensitive on every platform, `/` separators, and `*` may span `/`.
Matching directories are pruned. Patterns are not gitignore syntax.

Records sort by relative path; groups sort by first member path. JSON keys
are sorted and no generation timestamp or absolute root is included. Repeated
scans of unchanged files produce identical reports. File modification times
remain native filesystem metadata and can differ after copying/extraction.

## Limits and safety

This is a best-effort inventory, not an atomic snapshot. Hashing checks file
identity, size and modification time before and after reading, but concurrent
writers or adversarial path swaps can still race traversal. Do not scan a
tree controlled by an adversary while it is changing. File contents are read
in 1 MiB chunks; inventory metadata is kept in memory, so very large trees
may require substantial memory. Hard links are not deduplicated in byte totals.

Report parent paths are resolved before the outside-root check. Symlink report
paths are rejected. Forced replacement replaces the directory entry, which
avoids overwriting an input file through a hard link. Report directories must
already exist. No report is uploaded anywhere. Real filenames and metadata
can be personal information: inspect any report before sharing it.

## Code layout

- `scan.py`: traversal, exclusion rules, hash checks and duplicate grouping.
- `reports.py`: deterministic JSON/CSV and protected report writes.
- `__main__.py`: command-line parsing, summaries and exit codes.
- `tests/`: temporary synthetic filesystem tests and real CLI subprocesses.

Tests requiring OS permission to create symlinks skip when unavailable.
Windows junction handling follows the reparse-point flag; full cross-platform
and hostile-filesystem testing has not been performed.
