"""
QHDOpt GDP Formulation
======================

This module implements the Quantum Hamiltonian Descent Optimization (QHDOpt) problems
in Generalized Disjunctive Programming (GDP) formulation using Pyomo.

The QHDOpt framework is based on:
https://jiaqileng.github.io/quantum-hamiltonian-descent/nonconvex2d.html

Reference:
    Leng et al. - Quantum Hamiltonian Descent: A Novel Optimization Algorithm
    for Nonconvex Optimization Problems on Quantum Computers

GDP Formulation:
    This implementation uses Pyomo's GDP framework to model the problem with
    disjunctive constraints. The variables (x, y) are restricted to lie on a
    discrete lattice using disjunctions. These disjunctions can be transformed
    to Big-M MINLP formulations for solution with solvers like BARON or SCIP.

"""

import math
import pyomo.environ as pyo
from pyomo.gdp import Disjunct, Disjunction

BOUNDS = {
    "holder_table": (-10.0, 10.0, -10.0, 10.0),
    "deflected_corrugated_spring": (0.0, 10.0, 0.0, 10.0),
    "dropwave": (-5.12, 5.12, -5.12, 5.12),
    "levy": (-10.0, 10.0, -10.0, 10.0),
    "levy13": (-10.0, 10.0, -10.0, 10.0),
    "bohachevsky2": (-100.0, 100.0, -100.0, 100.0),
    "camel3": (-5.0, 5.0, -5.0, 5.0),
    "csendes": (-1.0, 1.0, -1.0, 1.0),
    "rosenbrock": (-2.0, 2.0, -1.0, 3.0),
    "michalewicz": (0.0, math.pi, 0.0, math.pi),
    "easom": (-10.0, 10.0, -10.0, 10.0),
    "xin_she_yang3": (-20.0, 20.0, -20.0, 20.0),
    "alpine1": (0.0, 10.0, 0.0, 10.0),
    "griewank": (-600.0, 600.0, -600.0, 600.0),
    "rastrigin": (-5.12, 5.12, -5.12, 5.12),
    "ackley": (-5.0, 5.0, -5.0, 5.0),
    "alpine2": (0.0, 1000.0, 0.0, 1000.0),
    "hosaki": (0.0, 5.0, 0.0, 6.0),
    "shubert": (0.0, 10.0, 0.0, 10.0),
    "styblinski_tang": (-5.0, 5.0, -5.0, 5.0),
    "sum_of_squares": (-10.0, 10.0, -10.0, 10.0),
}

def build_objective(m, name: str):
    """
    Return a Pyomo expression for the selected objective.
    """
    name = name.lower()

    if name == "ackley":
        return (
            -20 * pyo.exp(-0.2 * pyo.sqrt(0.5 * (m.x**2 + m.y**2)))
            - pyo.exp(0.5 * (pyo.cos(2 * math.pi * m.x) + pyo.cos(2 * math.pi * m.y)))
            + 20
            + pyo.exp(1)
        )
    elif name == "alpine1":
        return abs(m.x * pyo.sin(m.x) + 0.1 * m.x) + abs(
            m.y * pyo.sin(m.y) + 0.1 * m.y
        )
    elif name == "alpine2":
        return -pyo.sqrt(m.x * m.y) * pyo.sin(m.x) * pyo.sin(m.y)
    elif name == "bohachevsky2":
        return (
            m.x**2
            + 2 * m.y**2
            - 0.3 * pyo.cos(3 * math.pi * m.x) * pyo.cos(4 * math.pi * m.y)
            + 0.3
        )
    elif name == "camel3":
        return 2 * m.x**2 - 1.05 * m.x**4 + 1 / 6 * m.x**6 + m.x * m.y + m.y**2
    elif name == "csendes":
        eps = 1e-12
        return (
            m.x**6 * (2 + pyo.sin(1 / (m.x + eps)))**2
            + m.y**6 * (2 + pyo.sin(1 / (m.y + eps)))**2
        )
    elif name == "deflected_corrugated_spring":
        return 0.1 * ((m.x - 5) ** 2 + (m.y - 5) ** 2) - pyo.cos(
            5 * pyo.sqrt((m.x - 5) ** 2 + (m.y - 5) ** 2)
        )
    elif name == "dropwave":
        return -(1 + pyo.cos(12 * pyo.sqrt(m.x**2 + m.y**2))) / (
            0.5 * (m.x**2 + m.y**2) + 2
        )
    elif name == "easom":
        return (
            -pyo.cos(m.x) * pyo.cos(m.y)
            * pyo.exp(-((m.x - math.pi)**2 + (m.y - math.pi)**2))
        )
    elif name == "griewank":
        return (m.x**2 + m.y**2) / 4000 - pyo.cos(m.x) * pyo.cos(m.y / pyo.sqrt(2)) + 1
    elif name == "holder_table":
        return -abs(
            pyo.sin(m.x) * pyo.cos(m.y)
            * pyo.exp(abs(1 - pyo.sqrt(m.x**2 + m.y**2) / math.pi))
        )
    elif name == "hosaki":
        return (
            (1 - 8 * m.x + 7 * m.x**2 - 7 / 3 * m.x**3 + 1 / 4 * m.x**4)
            * m.y**2
            * pyo.exp(-m.y)
        )
    elif name == "levy":
        return (
            pyo.sin(math.pi * (1 + (m.x - 1) / 4)) ** 2
            + ((m.x - 1) / 4) ** 2
            * (1 + 10 * pyo.sin(math.pi * (1 + (m.x - 1) / 4) + 1) ** 2)
            + ((m.y - 1) / 4) ** 2
            * (1 + pyo.sin(2 * math.pi * (1 + (m.y - 1) / 4)) ** 2)
        )
    elif name == "levy13":
        return (
            pyo.sin(3 * math.pi * m.x) ** 2
            + (m.x - 1) ** 2 * (1 + pyo.sin(3 * math.pi * m.y) ** 2)
            + (m.y - 1) ** 2 * (1 + pyo.sin(2 * math.pi * m.y) ** 2)
        )
    elif name == "michalewicz":
        return -pyo.sin(m.x) * (pyo.sin(m.x**2 / math.pi) ** 20) - pyo.sin(m.y) * (
            pyo.sin(2 * m.y**2 / math.pi) ** 20
        )
    elif name == "rastrigin":
        return (
            m.x**2
            - 10 * pyo.cos(2 * math.pi * m.x)
            + m.y**2
            - 10 * pyo.cos(2 * math.pi * m.y)
            + 20
        )
    elif name == "rosenbrock":
        return (1 - m.x) ** 2 + 100 * (m.y - m.x**2) ** 2
    elif name == "shubert":
        return (
            pyo.cos(2 * m.x + 1) + 2 * pyo.cos(3 * m.x + 2) + 3 * pyo.cos(4 * m.x + 3)
        ) * (pyo.cos(2 * m.y + 1) + pyo.cos(m.y + 2))
    elif name == "styblinski_tang":
        return (
            (1 / 78)
            * 0.5
            * (m.x**4 - 16 * m.x**2 + 5 * m.x + m.y**4 - 16 * m.y**2 + 5 * m.y)
        )
    elif name == "sum_of_squares":
        return m.x**2 + 2 * m.y**2
    elif name == "xin_she_yang3":
        return (
            pyo.exp(-((m.x / 15) ** 6 + (m.y) ** 6))
            + 2 * pyo.exp(-(m.x**2 + m.y**2)) * pyo.cos(m.x)**2 * pyo.cos(m.y)**2
        )
    else:
        raise ValueError(f"Unknown objective function name: {name}")


def qhdopt_gdp(Npts=31, objective_name="alpine2", sense=pyo.minimize):
    """Create a QHDOpt GDP model for the specified objective function."""
    objective_name = objective_name.lower()
    if objective_name not in BOUNDS:
        raise ValueError(f"Unknown objective '{objective_name}'. Options: {sorted(BOUNDS)}")

    xmin, xmax, ymin, ymax = BOUNDS[objective_name]

    m = pyo.ConcreteModel()

    # Lattice index set: 0..Npts-1 (these are the integer lattice coordinates)
    m.I = pyo.RangeSet(0, Npts - 1)

    # Grid point coordinates in the *true domain* for this objective
    m.gx = pyo.Param(m.I, initialize=lambda m, i: xmin + (i / (Npts - 1)) * (xmax - xmin))
    m.gy = pyo.Param(m.I, initialize=lambda m, i: ymin + (i / (Npts - 1)) * (ymax - ymin))

    # Continuous decision variables (still GDP-restricted to gx/gy)
    m.x = pyo.Var(bounds=(xmin, xmax))
    m.y = pyo.Var(bounds=(ymin, ymax))

    # Integer lattice coordinates to print later (0..Npts-1)
    m.ix = pyo.Var(within=pyo.Integers, bounds=(0, Npts - 1))
    m.iy = pyo.Var(within=pyo.Integers, bounds=(0, Npts - 1))

    # --- Disjunction for x (chooses lattice point i, fixes both x and ix) ---
    m.Xchoice = Disjunct(m.I)
    for i in m.I:
        m.Xchoice[i].fix_x = pyo.Constraint(expr=m.x == m.gx[i])
        m.Xchoice[i].fix_ix = pyo.Constraint(expr=m.ix == i)
    m.pick_x = Disjunction(expr=[m.Xchoice[i] for i in m.I])

    # --- Disjunction for y (chooses lattice point j, fixes both y and iy) ---
    m.Ychoice = Disjunct(m.I)
    for j in m.I:
        m.Ychoice[j].fix_y = pyo.Constraint(expr=m.y == m.gy[j])
        m.Ychoice[j].fix_iy = pyo.Constraint(expr=m.iy == j)
    m.pick_y = Disjunction(expr=[m.Ychoice[j] for j in m.I])

    # Objective (selected)
    m.obj = pyo.Objective(expr=build_objective(m, objective_name), sense=sense)

    return m


if __name__ == "__main__":
    m = qhdopt_gdp(Npts=31, objective_name="levy13", sense=pyo.minimize)

    # Transform GDP -> MINLP (Big-M transformation)
    # This converts the disjunctions into mixed-integer constraints
    pyo.TransformationFactory("gdp.bigm").apply_to(m)
    solver = pyo.SolverFactory("gams")

    res = solver.solve(m, solver="scip", tee=True)

    print("\n" + "=" * 30)
    print("QHDOpt GDP Solution")
    print("=" * 30)
    print("lattice ix =", int(round(pyo.value(m.ix))))
    print("lattice iy =", int(round(pyo.value(m.iy))))
    print("x =", pyo.value(m.x))
    print("y =", pyo.value(m.y))
    print("obj =", pyo.value(m.obj))
    print("=" * 30)
