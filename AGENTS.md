# Repository Instructions

- Keep repository-facing text in English: code comments, docstrings, README updates, PR titles, PR descriptions, commit messages, review notes intended for GitHub, and user-visible library messages.
- Do not introduce Russian text or references to internal conversation language in this repository.
- Preserve Python 3.10+ runtime compatibility unless `pyproject.toml` is intentionally updated to raise the minimum supported version.
- Run `python -m pre_commit run --all-files` and `python -m pytest -q` before pushing PR updates.
