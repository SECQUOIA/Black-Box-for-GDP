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

import pyomo.environ as pyo
from pyomo.gdp import Disjunct, Disjunction


def qhdopt_gdp(Npts=31):
    """
    Create a QHDOpt GDP model with alpine2 function as the objective.
    
    The alpine2 function is a nonconvex benchmark problem used in optimization.
    It is optimized over a discrete lattice of Npts x Npts points.
    
    Parameters
    ----------
    Npts : int, optional
        Number of points in the lattice for each dimension (default: 31).
        The lattice points are: 0, 1, ..., Npts-1 (normalized to [0, 1000]).
        Total lattice includes 0, so technically it's a "31x31" lattice
        (indices from 0 to 30).
    
    Returns
    -------
    m : pyo.ConcreteModel
        A Pyomo ConcreteModel with the QHDOpt GDP formulation.
    
    Model Components
    ----------------
    - m.N : RangeSet [1, Npts] for indexing lattice points
    - m.g : Parameter array mapping indices to scaled values [0, 1000]
    - m.x, m.y : Continuous variables bounded in [0, 1000]
    - m.Xchoice, m.Ychoice : Disjunct blocks for x and y lattice selection
    - m.pick_x, m.pick_y : Disjunctions ensuring exactly one lattice point is selected
    - m.obj : Objective function (minimization of alpine2)
    
    Objective Function
    ------------------
    Minimizes: -sqrt(x*y) * sin(x) * sin(y)
    
    This is the alpine2 benchmark function. The negative sign is used because
    optimization algorithms typically minimize, but the original problem may
    seek maximum values in certain contexts.
    """
    m = pyo.ConcreteModel()

    # Define parameters
    # Create a lattice with Npts points uniformly distributed in [0, 1000]
    m.N = pyo.RangeSet(1, Npts)
    m.g = pyo.Param(
        m.N,
        initialize=lambda m, n: 1000.0 * (n - 1) / (Npts - 1),
        mutable=False
    )

    # Define variables
    # x and y are restricted to lattice points through disjunctions
    m.x = pyo.Var(bounds=(0, 1000))
    m.y = pyo.Var(bounds=(0, 1000))

    # --- Disjunction for x ---
    # Exactly one disjunct must be active, forcing x to take one of the lattice values
    m.Xchoice = Disjunct(m.N)
    for n in m.N:
        m.Xchoice[n].fix_x = pyo.Constraint(expr=m.x == m.g[n])
    m.pick_x = Disjunction(expr=[m.Xchoice[n] for n in m.N])

    # --- Disjunction for y ---
    # Exactly one disjunct must be active, forcing y to take one of the lattice values
    m.Ychoice = Disjunct(m.N)
    for n in m.N:
        m.Ychoice[n].fix_y = pyo.Constraint(expr=m.y == m.g[n])
    m.pick_y = Disjunction(expr=[m.Ychoice[n] for n in m.N])

    # Objective: Alpine2 function
    # Alpine2 is a nonconvex benchmark function with multiple local minima
    m.obj = pyo.Objective(
        expr=-pyo.sqrt(m.x * m.y) * pyo.sin(m.x) * pyo.sin(m.y),
        sense=pyo.minimize
    )

    return m

if __name__ == "__main__":
    """
    Example: Solve the QHDOpt GDP problem with alpine2 function.
    
    This script:
    1. Creates a GDP model for the alpine2 optimization problem
    2. Transforms the GDP into a Big-M MINLP formulation
    3. Solves using GAMS/SCIP solver
    4. Reports the optimal lattice point and objective value
    """
    m = qhdopt_gdp(Npts=31)

    # Transform GDP -> MINLP (Big-M transformation)
    # This converts the disjunctions into mixed-integer constraints
    pyo.TransformationFactory("gdp.bigm").apply_to(m)

    # Choose solver:
    # - BARON: Global solver for MINLP (commercial)
    # - SCIP: Open-source solver for MINLP
    # solver = pyo.SolverFactory("baron")
    solver = pyo.SolverFactory("gams")

    res = solver.solve(m, solver="scip", tee=True)

    print("\n" + "=" * 50)
    print("QHDOpt GDP Solution (Alpine2 Function)")
    print("=" * 50)
    print("x =", pyo.value(m.x))
    print("y =", pyo.value(m.y))
    print("obj =", pyo.value(m.obj))
    print("=" * 50)