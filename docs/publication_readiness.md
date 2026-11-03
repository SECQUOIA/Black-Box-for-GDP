# Public-release readiness review, November 3, 2026

The current files have been sanitized. The original GitHub repository remains
private, and its existing history still contains the removed license archive.
An isolated rewritten-history candidate has been prepared and verified before
any replacement of GitHub branch histories. Do not make the original repository
public while those historical copies remain reachable.

## Privacy cleanup

The audit found one GAMS license payload inside a superseded partial results
archive. That archive and its checksum sidecar were quarantined outside the
distributable tree, and the aggregate checksum index was updated. See the
[exact removal record](publication_sanitization.json) and
[preservation explanation](publication_sanitization.md).

All retained completed experiment records and original final return archives
are unchanged. The Process verifier reports the removal separately and permits
only the exact reviewed hash endpoints. Its current provider-code checksum was
updated in the companion index, retaining the previous provider hashes. It rejects restoration of the removed
paths, other evidence deletions and checksum-index edits.

Ignore rules now cover local environment settings, AWS/SSH directories, GAMS
license filenames, the removed archive, local review files, the local manuscript
export, and LaTeX intermediates. Existing local manuscript exports and build
files were preserved. Generated PDFs and bibliography sources remain available.

## Review scope and checks

The initial content scan covered the tracked tree and all 491 locally reachable
commits: 11,682 Git blobs, 223,124 file occurrences, and 134,725 deduplicated
payloads totaling 6,501,342,555 bytes. Archive inspection included recursive ZIP,
gzip and TAR contents. A separate pinned-submodule scan covered 964 file
occurrences, approximately 603 MB and 53 ZIP containers. The known GAMS license
was the only actual credential finding; other candidate matches were test or
detector literals and encoded image data. These are pattern-scan findings,
not a guarantee against every possible encoded secret or sensitive image.
The fresh GitHub mirror has 494 commits and 53 refs (13 branches and 40 managed
pull-request refs). Its additional objects contain no new blobs, so the content
findings cover its payloads too. The rewritten mirror passes strict Git integrity
checks; neither removed path nor the original archive blob remains in it.
An independent comparison of 488 available historical commit trees found only
the two documented file removals, with no other blob, mode or submodule changes.
See [the history report](publication_history.json) and
[original-to-clean commit map](publication_commit_map.tsv).

- Full local regression: 1,581 passed, 32 skipped, nine subtests passed and
  three optional GAMS integration failures. A no-solve startup probe reproduces
  the same exit 7 and network-license-session error. No other assertions failed.
- Separate pinned FMQA CPU environment: 66 tests passed.
- Sanitization, packaging, final-Process replay and frozen-companion tests: 29 passed, including
  the 560-run replay. The preservation audit confirms 46 unchanged archives
  and zero missing or changed retained experimental records.
- CI Ruff and reproduction Ruff checks passed.
- GitHub CI run [41676296494](https://github.com/SECQUOIA/Black-Box-for-GDP/actions/runs/41676296494)
  passed for the pre-cleanup reviewed source revision. This is separate from
  validation of the cleanup changes.
- No file in the reviewed tracked tree exceeds 100 MiB; the largest is
  approximately 59.44 MiB. The data-heavy tree is approximately 805 MiB.

## Documentation and source permissions

The root and manuscript guides now identify the current seven-method,
Lomustine and catalytic-distillation results. The frozen reproduction companion
is explicitly scoped to its October 19 four-method baseline. Historical
manuscript manifests, review excerpts and source ZIPs are labeled historical;
their old hashes are not presented as verification of current manuscript files.

[Third-party notices](../THIRD_PARTY_NOTICES.md) identify vendored FMQA and
model sources. The copied catalytic model now carries the exact upstream
license notice. The maintainer confirmed ownership and redistribution permission
for the pinned Dynamic source; its absent upstream license file is documented.

## Remaining release actions

1. Review the sanitized files and the isolated history-replacement candidate.
   Replacing existing GitHub branch histories requires explicit authorization;
   it changes commit IDs and affects collaborators' clones. GitHub-managed
   pull-request and cached objects require separate server-side handling.
2. Keep private backups private and coordinate with the license administrator
   about whether the embedded license should be replaced. History rewriting
   does not revoke a credential or erase independent copies.
3. Once history cleanup is complete, set visibility deliberately and verify
   manuscript snapshot links and all cited paths while logged out. Authenticated
   GitHub reads do not establish public access.
4. For a formal companion release, build from the exact cleaned commit, publish
   the ZIP and checksum to an immutable release/archival record, then download
   and run the documented commands. Issue #44's administrative closure did not
   certify these release/access checks.

The Python wheel builds, but some optional FMQA imports depend on helpers not
included in the wheel. The documented source-checkout installation is the
validated path; general standalone-wheel support remains separate work.

To build manuscript PDFs from clean sources, provide LaTeX, BibTeX, latexmk,
the packages used by the sources, and the Elsevier `elsarticle-harv.bst` style
(`kpsewhich elsarticle-harv.bst` should find it). Run `latexmk -pdf main.tex`
from `manuscript/`, then `latexmk -pdf supplementary.tex`. The first local
clean build stopped because that BibTeX style was absent. With the official
Elsevier style supplied from CTAN, both clean builds passed with no LaTeX,
reference or citation warnings: 61 pages combined and 30 pages supplementary,
matching the retained page counts. Rebuilt PDF text differs only in the updated
snapshot URL and abbreviated commit ID. Original PDFs were preserved privately.
