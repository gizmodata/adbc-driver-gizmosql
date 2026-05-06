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
- **Tags must always be `v`-prefixed** (e.g. `v1.1.6`, not `1.1.6`). bumpver tags as `{version}` with no prefix and offers no template for the tag name (see `bumpver/vcs.py` line ~242), so after every `bumpver update` you must retag:
  ```bash
  bumpver update --patch              # creates commit + tag '1.1.6'
  git tag -d 1.1.6                    # delete unprefixed tag
  git tag -a v1.1.6 -m "v1.1.6" HEAD  # recreate with v prefix
  git push origin main v1.1.6         # push commit + prefixed tag
  ```
  Older tags (1.1.1 / 1.1.2 / 1.1.3) lack the prefix; the project standardized on `v`-prefixed tags from v1.1.4 onward. CI's tag pattern (`*.*.*`) matches both, so PyPI publish still fires either way — but stay consistent with the prefix.
- Before bumping: move the `[Unreleased]` CHANGELOG section to a dated `[X.Y.Z]` section (separate commit) so the release commit is purely the version bump.
- GitHub Actions publishes to PyPI on release (OIDC trusted publishing)
