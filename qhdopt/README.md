# QHDOPT GDP - Quantum Hamiltonian Descent Optimization

## Source
Based on research from: [Quantum Hamiltonian Descent - Nonconvex 2D](https://jiaqileng.github.io/quantum-hamiltonian-descent/nonconvex2d.html)

## Overview
This folder implements the Quantum Hamiltonian Descent (QHD) algorithm with modifications for the GDP (Generalized Descent Problem) framework integrated with RBFopt.

## Key Modifications: Coordinate and Objective Function Scaling

### Coordinate Scaling
The integer grid coordinates are transformed to continuous domain before objective evaluation:

- **Original integer space**: x, y ∈ [0, 30] (31×31 grid)
- **Scaling factor**: `k = 1000/30 ≈ 33.333` (approximation shown for readability)
- **Transformed coordinates**: `x_continuous = x × k`, `y_continuous = y × k`
- **Result**: Continuous domain scaled to [0, 1000]

### Objective Function Scaling
The nonconvex objective function evaluated on scaled coordinates is then normalized:

- **Minimum objective value**: Scaled to **0**
- **Maximum objective value**: Scaled to **1** (using the greatest value from the evaluation grid)
- **Optimization goal**: Minimization

### Rationale
This two-stage scaling approach:
- Extends the search domain to provide finer gradient information
- Normalizes objective values for consistent algorithm behavior
- Improves numerical stability during gradient and descent computations
- Enables fair comparison across different problem instances
- Enhances convergence properties of the quantum descent dynamics

### Implementation
1. Apply coordinate transformation: `(x_c, y_c) = (x × 1000/30, y × 1000/30)`
2. Evaluate nonconvex objective on scaled coordinates
3. Identify minimum and maximum values from grid evaluations
4. Apply objective normalization: `f_scaled = (f - f_min) / (f_max - f_min)`
5. Solve minimization problem in normalized space [0, 1]

## Usage
Use the optimization routines in this folder for nonconvex 2D problems where quantum-inspired descent with scaled objectives improves solution quality and algorithmic stability.