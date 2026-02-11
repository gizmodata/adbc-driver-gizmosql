# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2025-02-11

### Added
- Initial release
- DBAPI 2.0 `connect()` with password and OAuth/SSO authentication
- OAuth browser flow via `get_oauth_token()` using only Python stdlib
- Auto-discovery of OAuth server endpoint (HTTPS with HTTP fallback)
- Re-export of all DBAPI 2.0 symbols from `adbc-driver-flightsql`
- Unit tests (mocked HTTP and ADBC) and integration tests (Docker)
- CI/CD with GitHub Actions and PyPI OIDC trusted publishing
