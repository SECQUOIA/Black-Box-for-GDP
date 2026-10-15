Verified CSTR20 and CSTR25 IPOPT evaluation return

Source: dantzig_cstr_box_ipopt_20261015_162507_3bnp0xm3.zip
Full archive: results/archives/ (archive SHA-256 and original path in import.json).
All 3,146 archive inventory hashes and all 1,025 CSV/point-JSON pairs were
checked. Objective, acceptance, coordinates and recorded times agree.

N=20: 400/400 coordinates processed; 210 accepted, 190 preprocessing_infeasible.
Best accepted IPOPT table value: 2.7994064251078212 at [20,20].
N=25: 625/625 coordinates processed; 325 accepted, 300 preprocessing_infeasible.
Best accepted IPOPT table value: 2.7814825926752516 at [25,25].
These are table minima, not claims of global GDP optimality.
All y<=x coordinates have an accepted record. All y>x coordinates have a
measured logical rejection. No pending records, duplicate keys or retries.

Initialization: mass_balance_zero_recycle, with the actual model size N.
The saved run configuration and original source are retained in the archive.
Acceptance requires successful GAMS solve status, optimal/local optimal model
status and termination, a finite objective and primal violation <=1e-5.
No acceptance thresholds or original records were changed during import.

total_wall_s and worker_process_wall_s are recorded for all coordinates.
For logical exclusions, solve_wall_s=0 denotes that no NLP solver was called;
missing setup/preprocess breakdowns remain missing. The full archive retains
the original JSON records, solver logs, source snapshot and SHA256SUMS.
