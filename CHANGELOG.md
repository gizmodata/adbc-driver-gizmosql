# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.4] - 2026-03-31

### Fixed
- `_is_ddl_dml()` now strips SQL block (`/* ... */`) and line (`-- ...`) comments before keyword detection. dbt's query comment prefix was preventing DDL/DML auto-detection, causing statements to go through the Flight SQL `PREPARE` path instead of `execute_update()`, which led to sporadic catalog errors on remote GizmoSQL instances.

## [1.1.0] - 2026-02-28

### Changed
- `cursor.execute()` now auto-detects DDL/DML statements by SQL keyword and executes them immediately on the server via the `DoPut` RPC, matching the behavior of the GizmoSQL JDBC and ODBC drivers. Previously, DDL/DML via `execute()` was never executed due to GizmoSQL's lazy-execution model (the `GetFlightInfo` RPC only plans, and `DoGet` is never called for DDL/DML).
- `cursor.execute_update()` remains available for explicit DDL/DML execution when the rows-affected count is needed as a return value.

## [1.0.0] - 2026-02-19

### Added
- `dbapi.execute_update(cursor, query)` — convenience function to execute DDL/DML statements immediately without fetching, bypassing GizmoSQL's lazy-execution model. Returns the number of rows affected.

## [0.1.0] - 2025-02-11

### Added
- Initial release
- DBAPI 2.0 `connect()` with password and OAuth/SSO authentication
- OAuth browser flow via `get_oauth_token()` using only Python stdlib
- Auto-discovery of OAuth server endpoint (HTTPS with HTTP fallback)
- Re-export of all DBAPI 2.0 symbols from `adbc-driver-flightsql`
- Unit tests (mocked HTTP and ADBC) and integration tests (Docker)
- CI/CD with GitHub Actions and PyPI OIDC trusted publishing
