# Redundant prose removed after the naming revision

This edit removes ten repeated sentences from the current main manuscript without adding replacement prose.
The abstract, section structure, equations, numerical results, tables, figure captions, conclusion and supplementary material are unchanged.
All substantive definitions and limitations remain at the locations listed below.
One sentence per source line is retained.

The baseline is commit `47b67d1f94a7b3ceef0eadcb459ce0c00d56f79d`.
The starting Overleaf source matches that baseline for the main source, supplementary source, bibliography and every manuscript figure PDF.
This is a prose-only revision and does not run or change any experiment or analysis.

## 1. Introduction, after the contribution list

Removed:

> Searches use frozen objective responses; the resulting cost estimates describe the recorded paths rather than measured online optimizer--NLP executions.

Retained coverage:

The abstract states the recorded-path versus online-execution distinction; the introduction already states that methods share frozen oracle responses; Sections 2.1 and 3.6 define the protocol and reconstructed costs.

## 2. 4.2, opening paragraph

Removed:

> Every actual callback, including a repeated visit, receives the cost of its coordinate under the accounting rules in Section~\ref{sec:cost-accounting}.

Retained coverage:

Section 3.6 explicitly charges initialization, repeated visits and preprocessing rejections; the Grid callback total and coordinate inventory remain in the preceding sentence.

## 3. 4.3.2, opening paragraph

Removed:

> Every callback, including unsuccessful and repeated evaluations, receives its saved cost using the complete case/size/configuration key.

Retained coverage:

Section 3.6 defines per-callback charging and the complete model/size/coordinate key; the result paragraph retains its 2,455-key inventory and 16,252-callback total.

## 4. 4.3.2, opening paragraph

Removed:

> Estimated full-run completion times are available for every seed.

Retained coverage:

Section 3.6 states that costs are available for all 700 primary Process runs; Figures 7 and 8 and Table 7 retain the complete-seed accounting.

## 5. 4.3.2, before the source reference

Removed:

> The costs combine recorded NLP evaluations with separately measured structural-rejection processing.

Retained coverage:

Section 3.6 names and counts the structural rejections and explains their separate measured costs; the reference to Supplementary Sections S4 and S8 remains.

## 6. 4.3.2, audit-scope paragraph

Removed:

> The audit establishes consistency of the retrospective cost reconstruction, not independent online replication or global optimality.

Retained coverage:

The preceding result paragraph still states that no original process NLP was rerun; Section 2.1 distinguishes accepted local-solver values from theoretical optima; Section 3.6 and the conclusion retain the retrospective-time limitation.

## 7. 4.3.2, audit-scope paragraph

Removed:

> Conclusions about search performance are conditional on this fixed local-solver oracle.

Retained coverage:

Sections 2.1 and 3.6 define the fixed oracle and point-cost inventory; Section 4.4 retains the initialization and acceptance-policy scope; the conclusion explicitly retains frozen local-solver responses.

## 8. 4.3.2, cost-share interpretation

Removed:

> The retained search-time component includes all operations retained within the method clock after subtracting measured lookup-processing time, rather than isolated surrogate-solving time.

Retained coverage:

The reconstruction equation in Section 3.6 subtracts lookup-call time, and the immediately following definitions explicitly include surrogate fitting, candidate generation, auxiliary optimization and recording in retained search time.

## 9. 4.4, opening paragraph

Removed:

> The initialization, fallback, and stopping diagnostics describe the complete implementations without isolating the causal benefit of surrogate learning.

Retained coverage:

The introduction explicitly identifies a descriptive decomposition rather than a causal ablation; the conclusion retains the statement that causal effects were not isolated; the BAM result paragraph retains its local qualification.

## 10. 4.4, final sentence

Removed:

> Hit counts and completion-cost distributions carry the primary evidence, with empirical TTS99 providing a secondary restart summary.

Retained coverage:

Section 3.6 already states that hit counts and completion-cost distributions are primary evidence and TTS99 is secondary; all numerical TTS interpretations and figure/table qualifications remain.
