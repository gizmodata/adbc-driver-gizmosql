# Claude Code Guidelines for adbc-driver-gizmosql

## Project Overview
A lightweight Python ADBC driver for GizmoSQL that wraps `adbc-driver-flightsql` with OAuth/SSO support.

## Build & Test Commands
```bash
# Install in editable mode with all extras
pip install --editable ".[dev,test]"

# Run unit tests only (no Docker required)
pytest tests/test_oauth_unit.py tests/test_connect_unit.py -v

# Run integration tests (requires Docker)
pytest tests/test_integration.py -v

# Run all tests
pytest -v

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Build distribution
python -m build
```

## Testing Policy
Integration tests (`tests/test_integration.py`) are very important. Any new or modified feature must have corresponding integration test coverage. Always run integration tests when making changes.

## Key Files
- `src/adbc_driver_gizmosql/_oauth.py` — OAuth browser flow (stdlib only)
- `src/adbc_driver_gizmosql/dbapi.py` — DBAPI 2.0 connect() wrapper
- `src/adbc_driver_gizmosql/__init__.py` — Public API exports
- `tests/conftest.py` — Docker test fixture

## Architecture
- OAuth uses GizmoSQL's server-side code exchange: `/oauth/initiate` → browser → `/oauth/token/{uuid}`
- All clients use Basic Auth for external tokens: `username="token"`, `password=<id_token_from_idp>`
- The `_oauth.py` module uses only stdlib (`urllib.request`, `json`, `ssl`, `webbrowser`)
- `dbapi.py` re-exports all DBAPI 2.0 symbols from `adbc_driver_flightsql.dbapi`

## Changelog
- **Always update `CHANGELOG.md`** when making changes — new features, bug fixes, breaking changes
- Follow [Keep a Changelog](https://keepachangelog.com/) format with `[Unreleased]` section
- When releasing, move `[Unreleased]` entries to a versioned section (e.g., `[1.1.0] - 2026-02-28`)
- CI skips on CHANGELOG-only changes (`paths-ignore`), but README changes still trigger CI (used by the Python packager)

## Version Management
- Version is in `pyproject.toml` and `src/adbc_driver_gizmosql/_version.py`
- Use `bumpver update --patch` (or `--minor`/`--major`) to bump — it auto-commits and tags
- GitHub Actions publishes to PyPI on release (OIDC trusted publishing)
