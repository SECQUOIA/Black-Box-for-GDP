# QHDOPT GDP - Quantum Hamiltonian Descent Optimization

## Source
Based on research from: [Quantum Hamiltonian Descent - Nonconvex 2D](https://jiaqileng.github.io/quantum-hamiltonian-descent/nonconvex2d.html)

## Overview
This folder implements the Quantum Hamiltonian Descent (QHD) algorithm with modifications for the GDP (Generalized Descent Problem) framework integrated with RBFopt.

## Key Modification: Objective Function Scaling

### Scaling Strategy
The objective function has been rescaled to normalize the optimization landscape:

- **Minimum objective value**: Scaled to **0**
- **Maximum objective value**: Scaled to **1** (using the greatest value from the evaluation grid)
- **Optimization goal**: Minimization

### Rationale
This normalization approach:
- Creates a bounded [0, 1] objective space for consistent algorithm behavior
- Improves numerical stability during gradient and descent computations
- Enables fair comparison across different problem instances
- Enhances convergence properties of the quantum descent dynamics

### Implementation
1. Evaluate objective function across the computational grid
2. Identify minimum and maximum values from grid evaluations
3. Apply linear transformation: `f_scaled = (f - f_min) / (f_max - f_min)`
4. Solve minimization problem in normalized space

## Usage
Use the optimization routines in this folder for nonconvex 2D problems where quantum-inspired descent with scaled objectives improves solution quality and algorithmic stability.