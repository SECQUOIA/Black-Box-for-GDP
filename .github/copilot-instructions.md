# GitHub Copilot Instructions for RBFopt_Test

## Project Context

This repository contains Jupyter notebooks for testing and demonstrating derivative-free optimization (DFO) techniques, primarily using the RBFopt library. The focus is on black-box optimization problems with integer and continuous variables.

## Key Libraries and Dependencies

- **RBFopt**: Main optimization library for radial basis function methods
- **NumPy**: Numerical operations and array manipulation
- **Pandas**: Data handling and CSV file operations
- **Matplotlib**: Visualization and plotting

## Common Patterns

### Loading Grid Data
```python
def load_grid(filename="data.csv"):
    grid_data = {}
    with open(filename, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            x = float(row["x"])
            y = float(row["y"])
            obj = float(row["Objective"])
            grid_data[(x, y)] = obj
    return grid_data
```

### Setting Up RBFopt Black Box
```python
black_box = rbfopt.RbfoptUserBlackBox(
    dimension,              # number of variables
    np.array([lower_bounds]),  # lower bounds
    np.array([upper_bounds]),  # upper bounds
    np.array(['I'] * dimension),  # variable types ('R' or 'I')
    obj_funct              # objective function
)
```

### Optimization Settings
```python
settings = rbfopt.RbfoptSettings(
    max_evaluations=100,
    algorithm='MSRSM',     # or 'Gutmann'
    print_solver_output=False
)
```

## File Naming Conventions

- **Notebooks**: `*_test*.ipynb` - Test notebooks with descriptive names
- **Data files**: `compl_enum_*_baron*.csv` - Pre-computed optimization results
- **Config files**: `OsiDefaultName_*` - Problem configuration files
- **Visualizations**: `gif/*.gif` - Animation outputs

## Code Suggestions

When suggesting code in this repository:

1. **Objective Functions**: Always handle penalties for infeasible points (use `np.inf`, `1e5`, or `np.nan`)
2. **Variable Bounds**: Check bounds from data files or OsiDefaultName_bounds
3. **Integer Variables**: Use 'I' type in RBFopt for discrete variables
4. **Data Loading**: Assume CSV files have headers: Point, x, y, Objective, Status, Time, Global_Time
5. **Error Handling**: Add warnings filter for NumPy longdouble type warnings
6. **Visualization**: Use matplotlib for plotting optimization trajectories and results

## Testing Approach

- Test notebooks should run end-to-end without errors
- Validate against pre-computed results in CSV files
- Check convergence and objective value improvements
- Generate visualizations to verify algorithm behavior

## Domain-Specific Knowledge

- **Black-box optimization**: No gradient information available
- **RBF methods**: Use radial basis functions for surrogate modeling
- **Integer constraints**: Variables must take discrete values
- **Penalty methods**: Handle infeasible points with large penalty values
- **BARON**: Referenced solver for baseline comparisons

## Common Issues to Avoid

1. Don't forget to handle missing data points in grid_data
2. Always set appropriate penalty values for infeasible points
3. Ensure variable types match the problem (integer vs continuous)
4. Check that bounds are correctly specified
5. Close file handles properly when loading data

## Helpful Context

- LDSDA: Local Derivative-free Successive Decomposition Algorithm (comparison method)
- MSRSM: Metric Stochastic Response Surface Method (RBFopt algorithm)
- Gutmann: Alternative RBFopt algorithm
- CSTR: Continuous Stirred Tank Reactor (application domain)
- Distillation Column: Another application domain for optimization tests
