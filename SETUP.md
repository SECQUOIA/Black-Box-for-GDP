# Setup Guide for RBFopt_Test

This guide will help you set up your development environment for working with the RBFopt_Test repository.

## Prerequisites

- Python 3.7 or higher
- pip (Python package manager)
- Git

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/SECQUOIA/RBFopt_Test.git
cd RBFopt_Test
```

### 2. Create a Virtual Environment (Recommended)

**On Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Verify Installation

Test that RBFopt is installed correctly:

```bash
python -c "import rbfopt; print(f'RBFopt version: {rbfopt.__version__}')"
```

### 5. Launch Jupyter

```bash
jupyter notebook
```

This will open a browser window where you can access and run the notebooks.

## Detailed Setup

### Installing RBFopt

RBFopt requires some additional system dependencies depending on your platform:

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y build-essential python3-dev
```

**macOS:**
```bash
brew install gcc
```

**Windows:**
- Install Microsoft Visual C++ Build Tools

### Optional: Installing Solvers

For enhanced functionality, you may want to install additional solvers:

- **BONMIN**: Open-source solver for MINLP problems
- **IPOPT**: Interior point optimizer
- **CPLEX**: Commercial solver (requires license)

Refer to the [RBFopt documentation](https://rbfopt.readthedocs.io/) for solver installation instructions.

## Troubleshooting

### Common Issues

**Issue: "No module named 'rbfopt'"**
- Solution: Ensure you've activated your virtual environment and run `pip install rbfopt`

**Issue: Jupyter kernel not found**
- Solution: Install ipykernel: `pip install ipykernel`
- Add kernel: `python -m ipykernel install --user --name=rbfopt_env`

**Issue: NumPy warnings about longdouble**
- Solution: These warnings are expected and can be safely ignored. They're filtered in the notebooks.

**Issue: CSV file not found**
- Solution: Ensure you're running notebooks from the repository root directory

### Performance Tips

1. **Use appropriate max_evaluations**: Start with 50-100 for testing
2. **Enable caching**: RBFopt caches function evaluations automatically
3. **Parallel execution**: RBFopt supports parallel evaluations (requires additional setup)
4. **Memory management**: Large CSV files may require significant memory

## Development Setup

If you plan to contribute to the repository:

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/SECQUOIA/RBFopt_Test.git
   ```
4. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```
5. **Make changes** and test thoroughly
6. **Submit a pull request** following CONTRIBUTING.md guidelines

## IDE Configuration

### VS Code

Recommended extensions:
- Python (Microsoft)
- Jupyter (Microsoft)
- GitHub Copilot (if available)
- GitLens

Settings for .vscode/settings.json:
```json
{
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "jupyter.askForKernelRestart": false,
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true
    }
}
```

### JupyterLab

For a more feature-rich notebook environment:
```bash
pip install jupyterlab
jupyter lab
```

## Next Steps

1. Read the [README.md](README.md) for project overview
2. Review [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines
3. Open and run `rbfopt_test.ipynb` to see a basic example
4. Explore other notebooks for more advanced use cases

## Getting Help

- **Issues**: Report bugs or request features via [GitHub Issues](https://github.com/SECQUOIA/RBFopt_Test/issues)
- **Discussions**: Ask questions in GitHub Discussions (if enabled)
- **RBFopt Docs**: [https://rbfopt.readthedocs.io/](https://rbfopt.readthedocs.io/)

## License

See the LICENSE file for licensing information.
