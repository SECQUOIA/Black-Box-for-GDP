# Frozen manuscript reproduction (Issue #44)

This guide and its retained validation reports describe the **October 19,
2026 four-method manuscript baseline**. The later seven-method manuscript,
Lomustine and catalytic-distillation results have separate reproduction guides
linked from [the current manuscript overview](../manuscript/README.md).
See [the publication readiness review](../docs/publication_readiness.md) for
the current release status.

This companion regenerates all eight main figures and the data for all eight
main tables and fifteen supplementary tables using **saved records only**.
It includes the authors' supporting data and complete algebraic audit. It does
not call RBFOpt, BAM, FMQA, IPOPT, BARON, Bonmin, GDPopt or enumeration.
The optional replay reconstructs archived paths and evaluates saved vectors
against their original GDP constraints; it does not optimize them.

The October 19 top-level `main.tex` and `supplementary.tex` supplied for review
are the reference. Their checksums, and those of the older nested manuscript
sources, are in [provenance.json](provenance.json). This frozen-data subset does
not include manuscript TeX, the Overleaf project ZIP or submission PDFs.
Current manuscript sources and PDFs are under [`manuscript/`](../manuscript/).
The package builder includes all committed files at the selected revision,
including manuscript files present at that revision. See [OUTPUT_INDEX.md](OUTPUT_INDEX.md)
for every output and [cited_files.json](cited_files.json) for cited file paths,
purpose, provenance and SHA-256.

## Reader commands: no solver or license required

Use CPython **3.12.13** (the validated version), or install it with `uv python
install 3.12.13`. From the root of a fresh checkout or extracted companion:

```bash
python3.12 -m venv /tmp/rbfopt-paper-env
/tmp/rbfopt-paper-env/bin/python -m pip install -r reproduction/requirements-lock.txt
# In a Git checkout only; a complete companion ZIP already includes these:
git submodule update --init --recursive
/tmp/rbfopt-paper-env/bin/python reproduction/reproduce.py --output /tmp/rbfopt-paper-output --replay
```

Choose a new empty output directory for every run. On Windows use the virtual
environment's `Scripts/python.exe`. The locked environment includes Pyomo for
saved-vector checking and SciPy for exact binomial intervals, but no optimizer
executables or proprietary BAM package. If only figure/table generation is
wanted, omit `--replay`. `--tables-only` skips plots. None of these commands
modifies retained results, original ZIPs or historical provenance.

The output contains eight PDFs and previews, 23 numbered CSV/Markdown table
datasets, full-precision interval data, plotted-value manifests, replay logs,
and `validation.json`. The report checks 560 Process runs (291 hits, 268 misses,
one failure), 4,200 Grid runs / 201,833 callbacks, 140 corrected BAM runs /
3,430 callbacks, 476 intervals, 14 terminal-only records and eleven bound
conflicts. It recomputes medians/TTS99 and checks them against frozen tables.
`--replay` also invokes the three official analyses and rechecks 63 saved GDP
vectors. Historical solver outcomes remain unchanged.

Tables are exported as long-form CSV and readable Markdown, not a copy of the
manuscript. Editorial operations are explicit: pivot by method, apply the
rounding in OUTPUT_INDEX, arrange panels, add mathematical notation, units,
footnotes and explanatory prose (especially Table 2). Full numerical precision
is retained. The figure renderers regenerate values and semantics; Figures 1,
3 and 5 have newly supplied layout code and are not byte-identical redraws of
the author-created PDFs. Figure 4 reuses the repository TTS99 values with the manuscript’s separate count/infinity strips; Figures 2,
6, 7 and 8 adapt the supplied companion renderers. Font/PDF library differences
can change layout and bytes. Figure 8 retains all 360 displayed points, all 36
ten-seed medians, and the one execution failure, now a **filled square**;
ordinary misses use crosses. Historical retained figures are not overwritten.

To compare an independently supplied manuscript (optional, not included):

```bash
/tmp/rbfopt-paper-env/bin/python reproduction/check_manuscript.py \
  --output /tmp/rbfopt-paper-output \
  --main /path/to/latest/main.tex --supplementary /path/to/latest/supplementary.tex
```

This checks displayed numeric cells and flags, writes a report, and fails on a
mismatch. It does not edit or copy either TeX file. Equations and explanatory
prose are not claimed to be automatically verified. See the retained
[validation report](validation/REPORT.md) for actual executed checks, limitations
and remaining release work.

## Pinned package creation and integrity

A maintainer builds the package from a **committed** revision, never the working
tree. Initialize submodules first; their exact gitlink commits are included:

```bash
python reproduction/package.py build --revision FULL_COMMIT_SHA --output /tmp/rbfopt-companion.zip
cd /tmp
shasum -a 256 -c rbfopt-companion.zip.sha256
mkdir rbfopt-companion
unzip -q rbfopt-companion.zip -d rbfopt-companion
cd rbfopt-companion
python reproduction/package.py verify --root .
```

The builder checks the selected committed tree and its pinned submodules before
creating a ZIP. It rejects known private solver-license filenames and the
superseded partial archive removed during the
[public-release privacy cleanup](../docs/publication_sanitization.md).
Use the sanitized publication history; an older private revision can still
contain that archive even when it is absent from the working tree.

The ZIP has normalized timestamps and includes `PACKAGE_MANIFEST.json` with
SHA-256 and size for every committed file, including expanded submodules.
Its sibling `.zip.sha256` covers the whole archive and `.package.json` records
the exact provider revision. It retains original execution revisions, raw
archives, runner packages, source/member hashes and recovery evidence. The
provider revision is distinct from the original Process execution revision
`ade67082ad2b09583a8f5594b827c97417e0ea99` and manuscript reference snapshot
`cb70771b2037301bb6d0e38a2362d49b53fcda7d`.

## Publication gate: deliberately still open

The reviewer observed a 404 for a process reproduction guide. That observation
does not establish whether the cause was visibility, a wrong path or a missing
file. Local package verification is not a logged-out access test.

- [ ] After merge, choose/tag the exact final commit and build its complete ZIP.
- [ ] Publish that ZIP and checksum to one fixed release/archival record; record
      the actual immutable download locator (none is invented in this PR).
- [ ] Download while logged out; verify the archive checksum, package root,
      every cited path and all reproduction guides. Record date, URL and result.
- [ ] Run the documented commands from that downloaded package and retain logs.
- [ ] Separately update the manuscript availability statement and Supplementary
      S8 to the immutable locator/output index. Refresh stale nested deployment
      archives only after checking them against the final top-level manuscript.
- [ ] Record completion of these public-access and manuscript conditions.
      Issue #44 was closed administratively; its
      [closure note](https://github.com/SECQUOIA/Black-Box-for-GDP/issues/44#issuecomment-6318113679)
      explicitly leaves final release and public-access verification as follow-up.

Live optimizer/NLP reruns described elsewhere in the repository are separate
experiments, need their original environments and sometimes licensed solvers,
and are **not** prerequisites for the commands above.

The supplied RBFOpt protocol shortens the two Dantzig executable paths to `bonmin` and `ipopt`; verification normalizes only those two basenames. Original absolute paths remain in the historical job metadata.
