# D-SDA publication update

The adopted Grid D-SDA records use strict absolute improvement greater than 1e-5 and the common reference-target predicate after each completed descent.
Budget exhaustion is checked first; a target observation does not interrupt a descent immediately.
The Process records use the same absolute improvement threshold and preserve their existing stopping policy.
These changes answer comments 4 and 5 while keeping objective improvement, target proximity, and primal feasibility conceptually separate.

Validation uses saved records only.
The Grid data-only audit passes for 1,050 runs and verifies 7,413 output hashes, 2,141 input hashes, and all callback/descent prefixes.
The Process return audit passes for all 1,190 source runs and verifies 6,378 output hashes and 263 input hashes.
The original comparison audit still passes for 3,430 jobs and 170,660 callbacks, with its original analysis outputs reproduced byte-for-byte.
The new publication tests and related Column, CSTR30, and comparison-audit tests pass (35 tests).
The publication analysis is reproduced in two fresh directories and all 30 generated files match byte-for-byte, including seven PDF figures.
All seven PDFs were rendered and visually inspected using the existing publication layout.
No optimization experiment, NLP solve, server run, or CI workflow was requested.

The [new publication analysis](../results/dsda_publication_20261028/README.md) provides run-level data, callback costs, paired summaries, figures, source hashes, and reproduction commands.
Historical result directories remain unchanged.
The current Overleaf source is edited locally in the editor and exported into the manuscript snapshot after verification.
Existing David comments and tracked changes are preserved.
