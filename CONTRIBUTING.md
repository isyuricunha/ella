# Contributing to Ella Mizuki

Thank you for your interest in contributing to Ella Mizuki! This document provides guidelines for contributing to this project.

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- Git

### Clone and Set Up

```bash
# Clone the repository
git clone https://github.com/isyuricunha/ella.git
cd ella

# Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install pytest
```

## 🧪 Running Tests

This project uses **pytest** for testing. Run the test suite with:

```bash
# Run all tests with verbose output
python3 -m pytest tests/ -v

# Run a specific test file
python3 -m pytest tests/test_agent.py -v

# Run tests with coverage (if coverage is installed)
python3 -m pytest tests/ --cov=.ella --cov-report=term-missing
```

The CI pipeline runs `python3 -m pytest tests/ -v` on every push and pull request.

## 📝 Code Style Expectations

- **Python**: Follow PEP 8 style guide. Use type hints where appropriate.
- **Conventional Commits**: Use conventional commit messages (e.g., `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`).
- **Small, focused changes**: Prefer small, single-purpose commits and PRs.
- **Tests**: Add tests for new functionality. Ensure all existing tests pass.

## 🔀 Submitting a Pull Request

1. **Fork** the repository to your own GitHub account.
2. **Create a branch** for your changes:
   ```bash
   git checkout -b my-feature-branch
   ```
3. **Make your changes** following the code style guidelines above.
4. **Run tests** to ensure everything works:
   ```bash
   python3 -m pytest tests/ -v
   ```
5. **Commit your changes** with a conventional commit message:
   ```bash
   git commit -m "feat: add new feature description"
   ```
6. **Push to your fork**:
   ```bash
   git push origin my-feature-branch
   ```
7. **Open a Pull Request** against the `main` branch of this repository.

### PR Guidelines

- Keep PRs focused on a single change or feature.
- Include a clear description of what the PR does and why.
- Reference any related issues (e.g., "Fixes #123").
- Ensure all CI checks pass before requesting review.

## 🐛 Reporting Issues

If you find a bug or have a feature request, please open an issue using the provided templates:
- **Bug Report**: For reporting bugs
- **Feature Request**: For suggesting new features

## 📄 License

By contributing to this project, you agree that your contributions will be licensed under the **GNU AGPLv3 License** (same as the project).