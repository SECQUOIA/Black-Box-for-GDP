# Analytic GDP models for the 21 benchmark grids

[`gdp_models/grid.py`](../gdp_models/grid.py) builds one independent Pyomo GDP
model for each CSV in [`benchmark_grids`](../benchmark_grids). The objective is
the analytic function used by the historical benchmark, evaluated at continuous
physical coordinates constrained to the same 31-by-31 grid. CSV objective values
are used for verification, not as coefficients in a table-selection objective.

The formulas and domains come from
[`qhdopt_gdp.py` at commit `11ba8728a107d6d16ed63e72d334a66662f9ebc1`](https://github.com/SECQUOIA/RBFopt_Test/blob/11ba8728a107d6d16ed63e72d334a66662f9ebc1/qhdopt_gdp.py).
These historical definitions include several variants of named benchmark
functions. Keeping those definitions is necessary to reproduce the existing
CSVs; substituting a canonical definition with the same function name can change
both the values and the minimizers.

## Feasible grid and objective

For CSV indices `i, j = 0, ..., 30`, physical coordinates are

```text
x(i) = xmin + (i / 30) * (xmax - xmin)
y(j) = ymin + (j / 30) * (ymax - ymin)
```

CSV `x` is the first coordinate and CSV `y` is the second. The mapping is not
transposed. The arithmetic order above follows the historical implementation.

Each model has two exclusive disjunctions: `pick_x` chooses one of 31
`Xchoice` branches, and `pick_y` chooses one of 31 `Ychoice` branches. They fix
`m.x` and `m.y` to the selected physical coordinates. The expressions `m.ix` and
`m.iy` recover their grid indices. Thus there are exactly 961 feasible coordinate
pairs for each of the 21 independent problems.

### Naïve GDP formulation

For each function $k$ in the domain table below, let $I=J=\{0,\ldots,30\}$,
$a_{ki}=\ell^x_k+i(u^x_k-\ell^x_k)/30$, and
$b_{kj}=\ell^y_k+j(u^y_k-\ell^y_k)/30$. One independent GDP is

$$
\begin{aligned}
\min_{x,y,Y^x,Y^y}\quad & F_k(x,y)=\frac{f_k(x,y)-L_k}{U_k-L_k} \\
\text{s.t.}\quad &
\bigvee_{i\in I}\left[\begin{array}{c}Y^x_i\\x=a_{ki}\end{array}\right],
\qquad
\bigvee_{j\in J}\left[\begin{array}{c}Y^y_j\\y=b_{kj}\end{array}\right],\\
& \operatorname{ExactlyOne}(Y^x_0,\ldots,Y^x_{30}),\qquad
\operatorname{ExactlyOne}(Y^y_0,\ldots,Y^y_{30}),\\
& \ell^x_k\le x\le u^x_k,\qquad \ell^y_k\le y\le u^y_k,\qquad
Y^x_i,Y^y_j\in\{\mathrm{False},\mathrm{True}\}.
\end{aligned}
$$

Here $f_k$ is the original analytic expression implemented in
[`_raw_expression`](../gdp_models/grid.py), and $L_k,U_k$ are its minimum and
maximum on the lattice. The two XOR disjunctions select exactly one pair
$(a_{ki},b_{kj})$. Conversely, every one of the 961 pairs satisfies the GDP by
activating its two coordinate branches. Thus its feasible objective values
and minimizers coincide with the sampled analytic function, subject to the
floating-point qualifications below. There are 62 Boolean indicators and two
physical continuous variables; Csendes additionally has two reciprocal
auxiliaries, also fixed by the branches.

This deliberately naïve formulation embeds a finite black-box search domain
in GDP. A DFO method selects $(i,j)$ and evaluates the corresponding fixed
GDP; a GDP solver receives the analytic expression and the disjunctions.
An arbitrary black-box oracle does not automatically provide derivatives or
an algebraic expression to GDPopt: the algebraic functions are available in
this particular benchmark. A 961-branch table-selection formulation would be
another finite-domain encoding, but is not the formulation timed here.

The original expressions are generally nonlinear and nonconvex. Big-M or Hull
reformulation therefore leads to an MINLP representation, not automatically
an MILP. The finite domain does permit a separate table-based MILP, but that
would replace the original-function objective with precomputed coefficients.

Once both indices are fixed, no original continuous degree of freedom remains.
The IPOPT measurements therefore characterize model preparation, GAMS/IPOPT
invocation and solution verification for a fixed function point. They do not
measure a difficult continuous subproblem. The
[path-cost comparison](../results/grid_gdp_dfo_20261011/README.md) uses that
explicit evaluation protocol consistently for every DFO callback.

Let `f` be the analytic objective, and let `fmin` and `fmax` be its minimum and
maximum obtained by evaluating all 961 grid points. The model exposes

```text
m.raw_objective = f(m.x, m.y)
m.obj = (f(m.x, m.y) - fmin) / (fmax - fmin)
```

The normalization constants come from the analytic function, not the CSV.
Positive affine normalization preserves the function's grid minimizers in exact
arithmetic and reproduces the CSV's `z_norm` values up to floating-point error.
It also means that preprocessing enumerates the grid and already supplies a
reference optimum. Any solver timing experiment should account for that
preprocessing separately and state whether the reference optimum is provided
to the solver.

## Historical domains

All intervals include both endpoints and have 31 equally spaced coordinates.

| Name | x interval | y interval |
|---|---|---|
| `ackley` | [-5, 5] | [-5, 5] |
| `alpine1` | [0, 10] | [0, 10] |
| `alpine2` | [0, 1000] | [0, 1000] |
| `bohachevsky2` | [-100, 100] | [-100, 100] |
| `camel3` | [-5, 5] | [-5, 5] |
| `csendes` | [-1, 1] | [-1, 1] |
| `deflected_corrugated_spring` | [0, 10] | [0, 10] |
| `dropwave` | [-5.12, 5.12] | [-5.12, 5.12] |
| `easom` | [-10, 10] | [-10, 10] |
| `griewank` | [-600, 600] | [-600, 600] |
| `holder_table` | [-10, 10] | [-10, 10] |
| `hosaki` | [0, 5] | [0, 6] |
| `levy` | [-10, 10] | [-10, 10] |
| `levy13` | [-10, 10] | [-10, 10] |
| `michalewicz` | [0, pi] | [0, pi] |
| `rastrigin` | [-5.12, 5.12] | [-5.12, 5.12] |
| `rosenbrock` | [-2, 2] | [-1, 3] |
| `shubert` | [0, 10] | [0, 10] |
| `styblinski_tang` | [-5, 5] | [-5, 5] |
| `sum_of_squares` | [-10, 10] | [-10, 10] |
| `xin_she_yang3` | [-20, 20] | [-20, 20] |

## Definitions that require particular care

`csendes` uses the historical squared variant

```text
f(x, y) = x^6 * (2 + sin(1/x))^2 + y^6 * (2 + sin(1/y))^2
```

Each coordinate term is defined as zero when that coordinate is zero, its
continuous limiting value. The implementation handles reciprocals through the
coordinate branches: the zero branch supplies a harmless zero auxiliary value;
nonzero branches supply the reciprocal of the selected coordinate. The
objective therefore contains no division by a variable that can be zero. The
historical source's `1/(x + 1e-12)` perturbation is not used; the exact reciprocal
with the zero extension reproduces the CSV within the validation tolerance.

`shubert` is the historical modified three-term/two-term product:

```text
(cos(2*x + 1) + 2*cos(3*x + 2) + 3*cos(4*x + 3))
* (cos(2*y + 1) + cos(y + 2))
```

`xin_she_yang3` is the historical variant

```text
exp(-((x/15)^6 + y^6))
+ 2*exp(-(x^2 + y^2))*cos(x)^2*cos(y)^2
```

The positive second term and the unscaled `y^6` are intentional compatibility
choices. Replacing them with the usual negative term and `(y/15)^6` would produce
a different optimization problem. In this CSV, the center is a maximum.

## Build and validate

Install the optional model and test dependencies, then run from the repository
root (no optimization solver is required):

```bash
python -m pip install ".[gdp,test]"
python -m pytest tests/test_grid_gdp.py -q
python -m gdp_models.grid list
python -m gdp_models.grid validate
python -m gdp_models.grid validate --names ackley rosenbrock --output /tmp/grid_audit.json
```

Validation checks every grid value against its corresponding CSV. Across all
21 problems this is 20,181 objective comparisons. The default absolute
comparison tolerance is `1e-12`.

```python
import pyomo.environ as pyo
from gdp_models.grid import (
    BOUNDS,
    GRID_NAMES,
    audit_grid,
    build_all_grid_gdps,
    build_grid_gdp,
    fix_grid_point,
)

report = audit_grid("rosenbrock", atol=1e-12)
m = build_grid_gdp("rosenbrock")  # verify_csv=True by default
fix_grid_point(m, (22, 14))
print(pyo.value(m.x), pyo.value(m.y))
print(pyo.value(m.raw_objective), pyo.value(m.obj))

# Each entry is a separate GDP model.
models = build_all_grid_gdps()
```

`build_grid_gdp` and `audit_grid` accept `csv_dir` to select a different CSV
directory. `build_grid_gdp(name, verify_csv=False)` skips CSV verification; it
still constructs the analytic objective and its grid normalization. Use the
default verification when comparing with the existing benchmark.

To prepare an unfixed model for a configured MINLP solver:

```python
import pyomo.environ as pyo
from gdp_models.grid import build_grid_gdp

m = build_grid_gdp("rosenbrock")
pyo.TransformationFactory("gdp.bigm").apply_to(m)

# Configure an installed solver and its options for your environment, then:
# results = solver.solve(m)
```

Construction, exhaustive grid verification, and successful GDP reformulation do
not establish that an arbitrary nonlinear solver will reach the global optimum.
These analytic expressions are nonconvex and include transcendental functions;
solver support, stopping tolerances, returned coordinates, and any global bound
must be checked for an actual solve. The exhaustive grid minimum is the
independent reference for checking a returned solution.

## Floating-point ties and underflow

Equality of the benchmark problems is checked numerically at every feasible
point. A single representative minimizer need not be the only acceptable
solution when several grid points tie.

For `rosenbrock`, indices `(22, 14)` and `(23, 16)` have the same analytic value
in exact arithmetic. The CSV stores normalized values of zero and approximately
`3.15e-19`, respectively. A strict floating-point `argmin` picks the first;
a tolerance-aware comparison recognizes the tie.

For `xin_she_yang3`, the CSV contains 12 exact zeros produced by exponential
underflow near the corners. Floating-point evaluation of the historical
analytic expression reproduces those zeros. In real arithmetic these values
are positive and the four corners are the minimizers. Thus the stored zero set
is a floating-point property, not a claim that all 12 analytic values are
mathematically equal. An absolute objective tolerance can also classify many
other extremely small positive values as tied; interpret the reported indices
and tolerance together.
