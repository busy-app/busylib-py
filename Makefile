.PHONY: help install install-dev test test-cov lint typecheck quality format clean build upload docs run-example

ifneq (,$(filter run-example,$(firstword $(MAKECMDGOALS))))
RUN_EXAMPLE_GOALS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
$(eval $(RUN_EXAMPLE_GOALS):;@:)
endif

# Default target
help:
	@echo "Available commands:"
	@echo "  install     - Install the package"
	@echo "  install-dev - Install in development mode with dev dependencies"
	@echo "  test        - Run tests"
	@echo "  test-cov    - Run tests with coverage"
	@echo "  lint        - Run pre-commit style lint checks (ruff + pyproject-fmt --check)"
	@echo "  typecheck   - Run pyright for src/busylib and tests"
	@echo "  quality     - Run full local quality gates (lint + typecheck + test)"
	@echo "  format      - Format code with ruff"
	@echo "  clean       - Clean build artifacts"
	@echo "  build       - Build package"
	@echo "  upload      - Upload to PyPI"
	@echo "  docs        - Generate documentation"
	@echo "  run-example - Run example main module via uv (usage: make run-example <name> [args...])"

# Install package
install:
	pip install .

# Install in development mode
install-dev:
	pip install --editable .[dev]

# Run tests
test:
	./.venv/bin/pytest -q

# Run tests with coverage
test-cov:
	./.venv/bin/pytest -q --cov=src/busylib --cov-report=term --cov-report=html

# Run linting
lint:
	./.venv/bin/ruff check src/busylib tests
	./.venv/bin/ruff format --check src/busylib tests
	./.venv/bin/pyproject-fmt --check pyproject.toml

# Run static typing checks
typecheck:
	./.venv/bin/pyright --pythonpath=.venv/bin/python src/busylib tests

# Run full quality gates
quality: lint typecheck test

# Format code
format:
	./.venv/bin/ruff format .

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Build package (requires build)
build: clean
	python -m build

# Upload to PyPI (requires twine)
upload: build
	twine upload dist/*

# Generate documentation (placeholder)
docs:
	@echo "Documentation generation not implemented yet"

# Run example by directory name via uv.
# Usage: make run-example remote -- --flag value
run-example:
	@EXAMPLE="$(word 1,$(RUN_EXAMPLE_GOALS))"; \
	ARGS="$(wordlist 2,$(words $(RUN_EXAMPLE_GOALS)),$(RUN_EXAMPLE_GOALS))"; \
	if [ -z "$$EXAMPLE" ]; then \
		echo "Usage: make run-example <name> [args...]"; \
		echo "Example: make run-example remote -- --help"; \
		exit 1; \
	fi; \
	uv run python -m "examples.$$EXAMPLE.main" $$ARGS
