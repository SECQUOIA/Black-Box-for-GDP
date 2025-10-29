# Contributing to RBFopt_Test

Thank you for your interest in contributing to RBFopt_Test! This document provides guidelines for contributing to the project.

## How to Contribute

### Reporting Issues

If you find a bug or have a suggestion for improvement:

1. Check the [existing issues](https://github.com/SECQUOIA/RBFopt_Test/issues) to avoid duplicates
2. Use the appropriate issue template (Bug Report, Feature Request, or Documentation)
3. Provide clear and detailed information
4. Include relevant code snippets, error messages, or screenshots

### Submitting Changes

1. **Fork the repository** and create a new branch from `main`
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Follow the existing code style
   - Add comments for complex logic
   - Update documentation as needed

3. **Test your changes**
   - Run all affected notebooks to ensure they work correctly
   - Verify that no new errors or warnings are introduced
   - Test with different parameter configurations if applicable

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "Brief description of changes"
   ```

5. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create a Pull Request**
   - Use the pull request template
   - Reference any related issues
   - Provide a clear description of the changes

## Development Guidelines

### Jupyter Notebooks

- **Clear outputs** before committing to reduce file size (optional but recommended)
- Use **markdown cells** to document the purpose of code sections
- Include **visualizations** where appropriate to illustrate results
- Keep notebooks **focused** on a specific optimization problem or technique

### Python Code

- Follow **PEP 8** style guidelines
- Use **meaningful variable names**
- Add **docstrings** to functions
- Handle **exceptions** appropriately
- Avoid **hardcoded paths** - use relative paths or configuration

### Data Files

- Use **CSV format** for structured data
- Include **column headers** in CSV files
- Document the **format and meaning** of data files in comments or README
- Keep file sizes reasonable (compress large files if necessary)

### Documentation

- Keep the **README.md** up to date
- Document **new features** or changes in behavior
- Include **usage examples** for new functionality
- Update **issue templates** if new categories are needed

## Code Review Process

1. All contributions require review before merging
2. Reviewers will check:
   - Code quality and style
   - Functionality and correctness
   - Documentation completeness
   - Test coverage
3. Address reviewer feedback promptly
4. Be open to suggestions and constructive criticism

## Style Guidelines

### Commit Messages

- Use clear, descriptive commit messages
- Start with a verb in present tense (e.g., "Add", "Fix", "Update")
- Keep the first line under 72 characters
- Add detailed description in the body if needed

Example:
```
Add batch optimization example notebook

- Demonstrates RBFopt usage with batch problems
- Includes visualization of convergence
- Uses small_batch_baron.csv data file
```

### Branch Naming

- Use descriptive branch names
- Prefix with type: `feature/`, `bugfix/`, `docs/`, `refactor/`
- Use hyphens to separate words

Examples:
- `feature/add-constrained-optimization`
- `bugfix/fix-csv-loading-error`
- `docs/update-installation-guide`

## Questions?

If you have questions about contributing, feel free to:
- Open an issue with your question
- Reach out to the maintainers
- Check existing documentation and issues for answers

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the code, not the person
- Help create a welcoming environment for all contributors

Thank you for contributing to RBFopt_Test!
