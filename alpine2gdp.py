import pyomo.environ as pyo
from pyomo.gdp import Disjunct, Disjunction

def alpine2_gdp(Npts=31):
    m = pyo.ConcreteModel()

    # Define parameters
    m.N = pyo.RangeSet(1, Npts)
    m.g = pyo.Param(m.N, initialize=lambda m, n: 1000.0 * (n - 1) / (Npts - 1), mutable=False)

    # Define variables
    m.x = pyo.Var(bounds=(0, 1000))
    m.y = pyo.Var(bounds=(0, 1000))

    # --- Disjunction for x ---
    m.Xchoice = Disjunct(m.N)
    for n in m.N:
        m.Xchoice[n].fix_x = pyo.Constraint(expr=m.x == m.g[n])
    m.pick_x = Disjunction(expr=[m.Xchoice[n] for n in m.N])

    # --- Disjunction for y ---
    m.Ychoice = Disjunct(m.N)
    for n in m.N:
        m.Ychoice[n].fix_y = pyo.Constraint(expr=m.y == m.g[n])
    m.pick_y = Disjunction(expr=[m.Ychoice[n] for n in m.N])

    # Objective, the objective can be modified based on which QHDOpt problem you want to solve
    m.obj = pyo.Objective(
        expr= -pyo.sqrt(m.x * m.y) * pyo.sin(m.x) * pyo.sin(m.y),
        sense=pyo.minimize
    )

    return m

if __name__ == "__main__":
    m = alpine2_gdp(Npts=31)

    # Option A: transform GDP -> MINLP (Big-M), then solve with BARON / KNITRO
    pyo.TransformationFactory("gdp.bigm").apply_to(m)

    # Choose one:
    # solver = pyo.SolverFactory("baron")
    solver = pyo.SolverFactory("gams")

    res = solver.solve(m, solver='scip', tee=True)

    print("\nSolution:")
    print("x =", pyo.value(m.x))
    print("y =", pyo.value(m.y))
    print("obj =", pyo.value(m.obj))