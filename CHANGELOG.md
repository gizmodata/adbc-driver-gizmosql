# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.7] - 2026-05-10

### Changed
- Switched the integration-test fixture from Docker
  (`gizmodata/gizmosql:latest`) to the
  [`gizmosql`](https://pypi.org/project/gizmosql/) PyPI package's
  managed subprocess. The fixture mints a session-scoped self-signed
  TLS cert via `cryptography` and passes it through `--tls`, preserving
  the `grpc+tls://` connection contract used by the integration tests.
  Replaced `docker` with `gizmosql>=1.26.0,<2` and `cryptography>=42`
  in the `[test]` extra. Local development no longer requires Docker.

## [1.1.6] - 2026-05-06

### Fixed
- `cursor.execute()` now correctly handles `INSERT/UPDATE/DELETE ... RETURNING` ([#3](https://github.com/gizmodata/adbc-driver-gizmosql/issues/3), originally [gizmosql#163](https://github.com/gizmodata/gizmosql/issues/163)). Previously the SQL was unconditionally routed through `execute_update()` (the server's `DoPut` RPC) on the basis of the leading keyword, which only returns a row count and silently discards the rows produced by the `RETURNING` clause — so `cursor.fetch_arrow_table()` afterwards raised `Cannot fetch_arrow_table() before execute()`. DML with a `RETURNING` clause now takes the regular `GetFlightInfo` → `DoGet` query path, and the result is **eagerly materialized** so the underlying DML actually fires regardless of whether the caller chooses to fetch — this preserves the same "execute means execute now" guarantee the original DDL/DML keyword split was added for, while making the returned rows available via `fetch_arrow_table()` / `fetchall()` / `description` / `rowcount`. `RETURNING` detection strips comments and string literals first, so values like `INSERT INTO t VALUES ('returning')` are not misclassified.

## [1.1.5] - 2026-03-31

### Fixed
- `adbc_get_info()` is now thread-safe. Concurrent calls to `adbc_get_info()` on the Go ADBC Flight SQL driver crash with `"fatal error: concurrent map writes"` (apache/arrow-adbc#1178). The result is now cached behind a lock so the underlying call happens exactly once.

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
