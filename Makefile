.PHONY: help install install-dev test test-cov lint format clean build upload docs

# Default target
help:
	@echo "Available commands:"
	@echo "  install     - Install the package"
	@echo "  install-dev - Install in development mode with dev dependencies"
	@echo "  test        - Run tests"
	@echo "  test-cov    - Run tests with coverage"
	@echo "  lint        - Run linting checks"
	@echo "  format      - Format code with black"
	@echo "  clean       - Clean build artifacts"
	@echo "  build       - Build package"
	@echo "  upload      - Upload to PyPI"
	@echo "  docs        - Generate documentation"

# Install package
install:
	pip install .

# Install in development mode
install-dev:
	pip install --editable .[dev]

# Run tests
test:
	python -m pytest tests/ -v

# Run tests with coverage
test-cov:
	# python -m pytest tests/ -v --cov=busylib --cov-report=html --cov-report=term
	@echo "Not implemented yet"

# Run linting
lint:
	@echo "Not implemented yet"

# Format code
format:
	ruff format .

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
