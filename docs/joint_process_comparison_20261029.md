# Joint DFO and algebraic process comparison

The exploratory comparison is added to Supplementary Section S9 for review before any decision to move it into the main results.
It adds Table S8 and Figures S1 and S2 using existing records only.
The [analysis and reproduction command](../results/joint_process_comparison_20261029/README.md) accompany the [generator](../review_comparison/joint_process.py) and [tests](../tests/test_joint_process.py).

The inputs contain 700 primary DFO runs over fourteen conditions and 45 algebraic runs over nine problems.
The two figures show every DFO seed and one observation for each algebraic execution, with target outcomes retained.
The six Dynamic panels repeat the same five algebraic observations for reference and do not create new replicates.
DFO completion costs are reconstructed estimates; algebraic completion times include measured preparation.
The original target predicates are retained and stated in S9.
No single-run algebraic success probability or statistical superiority claim is introduced.

All 16,041 DFO callbacks match the current publication coverage ledger.
There are 10,114 corresponding fixed-configuration NLP evaluations, including rejected NLP returns, and 5,927 logical or preprocessing rejections without an NLP solve.
GDPopt has 2,236 confirmed SCIP NLP interface calls across the 27 runs.
The CSTR25 LOA and CSTR30 RIC unconfirmed NLP attempts are reported separately.
Direct Big-M and Hull internal NLP counts are unavailable and are not encoded as zero.
The table uses median DFO counts and single-execution GDPopt counts; it does not equate formulation difficulty or internal iterations.

The new tests reject missing or duplicated runs and callbacks, distinguish preprocessing from rejected NLP returns, preserve the single algebraic observations, and verify the archived counts and bound flags.
The new and related tests pass: 25 tests and two subtests.
Ruff passes for the two new Python files.
Two fresh analysis runs produce ten byte-identical outputs, including both PDFs and all CSV files.
Input hashes are checked against the archived manifests and checksum inventories.
Original experiment archives, execution-provider revisions, and historical analysis outputs are unchanged.
No optimization, server experiment, or NLP evaluation is executed.

Overleaf remains the manuscript source of truth.
The supplement was edited in place, preserving existing text, comments, and tracked edits.
Only new figure PDFs were uploaded; no TeX source was uploaded to replace an Overleaf document.
The live main source is unchanged by this task.
The repository snapshot also captures the previously completed Overleaf story revisions that postdate the earlier Grid-only snapshot.
The combined PDF has 34 pages and S9 occupies pages 32--34.
The final combined compile reports zero errors and zero warnings.

```sh
python -m review_comparison.joint_process --output /tmp/joint-process-check
python -m pytest tests/test_joint_process.py tests/test_grid_presentation.py tests/test_dsda_publication.py -q
python -m ruff check review_comparison/joint_process.py tests/test_joint_process.py
```
