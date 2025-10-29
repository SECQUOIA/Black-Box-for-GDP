# RBFopt_Test

Test repository for Derivative-Free Optimization (DFO) using RBFopt and other optimization methods.

## Overview

This repository contains Jupyter notebooks and test data for exploring derivative-free optimization techniques, particularly focusing on RBFopt (Radial Basis Function Optimization) for solving black-box optimization problems with integer and continuous variables.

## Repository Structure

```
.
├── README.md                          # This file
├── .gitignore                         # Git ignore patterns
│
├── Jupyter Notebooks                  # Optimization experiments
│   ├── rbfopt_test.ipynb             # Main RBFopt test notebook
│   ├── rbfopt_test_batch.ipynb       # Batch optimization tests
│   ├── rbfopt_test_column.ipynb      # Column optimization tests
│   ├── rbfopt_test_dynamic.ipynb     # Dynamic optimization tests
│   ├── dfoopt_test_5.ipynb           # DFO test with 5 constraints
│   ├── dfoopt_test_8.ipynb           # DFO test with 8 constraints
│   └── dfoopt_test17.ipynb           # DFO test with 17 variables
│
├── Data Files                         # Pre-computed optimization results
│   ├── compl_enum_column_17_baron.csv           # Column problem results
│   ├── compl_enum_small_batch_baron.csv         # Small batch results
│   └── compl_enum_cstr_*_baron_hull.csv         # Constraint hull results (5-30)
│
├── Configuration Files                # Problem setup
│   ├── OsiDefaultName_bounds         # Variable bounds definition
│   └── OsiDefaultName_start          # Starting point configuration
│
└── gif/                              # Visualization outputs
    ├── cstr_ldsda_trajectory.gif
    ├── cstr_rbfopt_iteration1_start.gif
    ├── distillation_ldsda.gif
    ├── distillation_rbfopt_iteration1_start.gif
    ├── dynamic_ldsda.gif
    ├── dynamic_rbfopt_iteration1_start.gif
    └── ldsda_trajectory_unified_dots.gif
```

## Prerequisites

To run the notebooks in this repository, you need:

- Python 3.7+
- Jupyter Notebook or JupyterLab
- Required Python packages:
  - `rbfopt` - Radial Basis Function optimization library
  - `numpy` - Numerical computing
  - `matplotlib` - Plotting and visualization
  - `pandas` - Data manipulation (for CSV handling)

## Installation

```bash
# Install required packages
pip install rbfopt numpy matplotlib pandas jupyter

# Clone the repository
git clone https://github.com/SECQUOIA/RBFopt_Test.git
cd RBFopt_Test

# Launch Jupyter
jupyter notebook
```

## Usage

### Running the Notebooks

1. **Main RBFopt Test** (`rbfopt_test.ipynb`):
   - Demonstrates basic RBFopt usage with integer variables
   - Loads pre-computed grid data from CSV files
   - Solves black-box optimization problems

2. **Batch Optimization** (`rbfopt_test_batch.ipynb`):
   - Tests batch optimization scenarios
   - Uses small batch problem data

3. **Column Optimization** (`rbfopt_test_column.ipynb`):
   - Solves column design optimization problems
   - Uses 17-variable test case

4. **Dynamic Optimization** (`rbfopt_test_dynamic.ipynb`):
   - Explores dynamic optimization problems
   - Generates visualization outputs

5. **DFO Tests** (`dfoopt_test_*.ipynb`):
   - Various derivative-free optimization experiments
   - Tests with different numbers of constraints and variables

### Data Files

The CSV files contain pre-computed optimization results with columns:
- `Point`: Point identifier
- `x`, `y`: Decision variables
- `Objective`: Objective function value
- `Status`: Optimization status
- `Time`: Computation time
- `Global_Time`: Cumulative time

These files are used as reference data for black-box function evaluations.

## Problem Types

The repository includes tests for:
- **Integer programming problems**: Optimization with discrete variables
- **Mixed-integer problems**: Combination of continuous and discrete variables
- **Black-box optimization**: Problems where gradient information is unavailable
- **Constrained optimization**: Problems with equality/inequality constraints

## Visualization

The `gif/` directory contains animated visualizations showing:
- Optimization trajectories
- Algorithm iterations
- Convergence behavior
- Different optimization strategies (RBFopt vs LDSDA)

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## References

- [RBFopt Documentation](https://rbfopt.readthedocs.io/)
- [RBFopt Paper](https://link.springer.com/article/10.1007/s12532-017-0130-5)

## License

Please refer to the repository license for usage terms.
