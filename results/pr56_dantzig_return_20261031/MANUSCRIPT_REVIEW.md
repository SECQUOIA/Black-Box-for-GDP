# Manuscript review notes for the completed PR #56 return

Prepared against `c4d7db6b671bbe92a314be524a650d75cd49529c`. Line references below refer to that revision. **No manuscript or Overleaf edits have been applied.** The source branch was read without checkout, reset, stash, or modification. The new results accompany this PR; the proposed manuscript edits below remain unapplied.

## Findings that change the interpretation

1. **The expanded Grid ranking differs.** `manuscript/main.tex:710` says RBFOpt reaches the most targets from B=30 onward. With MISO included, MISO leads at B=30/70/100, RBFOpt at B=50, and BAM at B=10. The final-fraction claim in the Grid profile caption near line 744 also requires revision. At B=100: MISO 86.2%, RBFOpt 81.4%, BAM 70.0%, FMQA-SA 61.4%, NOMAD 60.0% under the frozen crash policy, D-SDA 48.1%, Uniform 21.4%. The BAM prefix control must remain explicitly labeled if retained in a figure.

   Suggested replacement: “MISO reaches the largest observed target fraction at budgets 30, 70, and 100, while RBFOpt leads at 50 and BAM at 10. At 100 evaluations, MISO and RBFOpt reach 86.2% and 81.4% of the targets, respectively.” This is a descriptive result, not a statistical dominance claim.

2. **D-SDA's target-hit outcome is unchanged, but its best objective sometimes improves.** `main.tex:592` and `main.tex:808` currently use “changes none of the outcomes.” The 22 changes reported by the server are 11 unique condition–seed jobs, each improved by both restart variants. None crosses the target threshold. The 11 before/after pairs are in `dsda_changes.csv` (22 rows because variants are separate).

   Suggested replacement: “Restarting from the remaining shared initial configurations or from uniformly drawn unvisited configurations leaves target attainment unchanged at 74 of 140 runs. Both restart variants nevertheless improve the final best objective in 11 runs, all of which remain target misses.”

3. **The methods section and cohort size must match any expanded main comparison.** The abstract's list at `main.tex:73`, the three-surrogate-method discussion at line 220, and process count at lines 351/406/560 need updating if NOMAD/MISO become primary methods. MISO is a surrogate method; NOMAD is direct search. The seven-method Process cohort has 980 jobs, 21,777 callback visits, and 2,106 distinct configuration keys. The original five-method cohort is still correctly described by 700 jobs, 16,041 callbacks, and 2,024 keys if it remains a separately labeled cohort. Do not combine both descriptions in the same table or caption.

4. **The RBFOpt result remains valid but is no longer the only strong surrogate result.** The abstract's RBFOpt CSTR 45/60 and CSTR30 9/10 with median 31.5 NLP-work equivalents remain numerically correct. MISO reaches CSTR 43/60, including CSTR30 10/10 with median 29.5, and Column 10/10. A balanced revision should mention both strengths and costs: MISO has poorer small-CSTR attainment and greater search overhead on several conditions. At Dynamic/B50, MISO and RBFOpt both hit 10/10, but median reconstructed completion times are 195.36 s and 65.14 s. The discussion around lines759–773 should reflect these results instead of extending RBFOpt-specific explanations to every surrogate.

5. **NOMAD's implementation failure is separate from target attainment.** Add the three terminal status groups, the 21 repeated crashes, and the strict 602 versus adopted 618 overall sensitivity. All 21 crashes occur at Grid/B100; 16 have already reached the target. A success profile may score those16 paths under the frozen protocol, but the text must also identify that their native executions never completed normally. Time plots must retain missingness:21 unavailable times, all at B100;NOMAD timing summaries there use 189 observations. Do not label the runner's `execution_failures=0` as “zero native crashes.”

6. **New exploratory statistics do not establish universal superiority.** The prepared analysis tests five contrasts in each of 14 conditions, Holm-corrected over 70 tests. None survives correction. The Column MISO–RBFOpt contrast is 6:0 discordant pairs, raw p=.03125, adjusted p=1.0. These tests were defined during returned-data analysis, not preregistered. Keep that family explicit and distinct from the manuscript's existing RBFOpt–D-SDA tests. Repeated Dynamic budgets are not additional independent replicates. Lack of significance does not establish equivalence; the abstract's “statistically indistinguishable” wording also merits precision.

## Timing and provenance updates now supported by evidence

- `main.tex:593` and `supplementary.tex:685` contain notes awaiting Dantzig timing. The completed return supplies those times; remove the pending language when actually integrating the results. Use `dsda_conditions.csv` for the restart table and `process_conditions.csv` for the expanded comparison. All median/quartile values are computed over individual runs.
- The supplementary restart section near line653 already correctly says no target hit changes. Add the 11 objective-improvement cases and distinguish the two restart variants' extra 930/959 evaluations. The new D-SDA replay is a diagnostic; do not count its 140 single-descent records as another independent baseline sample.
- The Process NLP-work and timing plots, Grid success profile, search-overhead tables, method palette/legend, and statistics table need regeneration from the expanded per-run cohort if the methods are incorporated. The two figures prepared here are standalone analysis figures; existing manuscript figures remain unchanged.
- `nlp_solves` in the lookup runs counts stored NLP-work equivalents, not new solves. Reconstructed completion includes stored preparation and per-callback historical point costs plus measured retained search time. It is not online NLP time or time to target. NOMAD rerun times represent the selected successful attempt; failed-attempt overhead is not recoverable per job.
- Preserve method-specific stopping. Published Grid D-SDA has a target checkpoint; NOMAD/MISO do not stop using the reference target. Do not describe all methods as using identical stopping rules simply because budgets and starts match.
- Record the source revision, server Python/package versions, six physical-core assignments, nonexclusive scheduling, input hash, return hash, and missing timing denominator in the supplement or reproducibility appendix.

## Pre-return PR description cleanup

Before this result addition, the PR body reported incomplete workstation cohorts (MISO 491 / NOMAD 394), eight terminal NOMAD failures, and a pending decision about path scoring. Those statements are superseded by the returned campaign and the policy already implemented at the experiment revision. The completed-return section replaces those obsolete sections and corrects the D-SDA “none of the outcomes” shorthand.

The old partial workstation statement has MISO Grid/B30 at 140/210; the completed frozen-revision Dantzig return has 141/210. The report uses the actual Dantzig records. It does not force agreement with the earlier partial result, and the available return alone does not establish the cause of that difference.

A prior “10+ hours” estimate for MISO/B100 should not be reported as measured runtime or as the denominator of a claimed parallel speedup. All 210 Grid/B100 jobs completed their full 100-evaluation budget. Ten seed bundles used up to five physical cores, with 1 h 54 min 31 s of summed bundle duration over a 31 min 56 s observed span. The remaining difference from the estimate cannot be attributed without its original environment and measurement basis.

## Integration boundary

This result addition contains only new artifacts and analysis/test scripts. It does not change the optimizer, launcher, existing baseline tables, or manuscript. Its numerical data are ready for review. The author's choice of main-text versus supplementary placement and the corresponding prose/figure integration remain unapplied review work, rather than an unperformed experiment.
