# Copilot Instructions for e2n

This file guides AI coding assistance in this repository.

## Project Overview
- `e2n` converts Evernote exports to Notion-ready pages and database row entries.
- Core package path: `src/e2n`.
- Tests live in `tests`.

## Coding Guidelines
- Prefer small, focused functions.
- Preserve existing CLI behavior and option names.
- Add or update tests for behavioral changes.
- Keep error messages actionable and specific.

## Python Conventions
- Target Python configured in `pyproject.toml`.
- Use type hints where practical.
- Raise project-specific exceptions from `src/e2n/exceptions.py` when appropriate.

## Testing
- Run tests with `pytest`.
- For parser and converter changes, prioritize tests in:
  - `tests/test_enml.py`
  - `tests/test_enex_extraction.py`
  - `tests/test_notion.py`

## Documentation
- Update `README.md` and files in `docs/` when behavior or usage changes.
