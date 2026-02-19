# adbc-driver-gizmosql
A Python [ADBC](https://arrow.apache.org/adbc/) driver for [GizmoSQL](https://gizmodata.com/gizmosql) with OAuth/SSO support

[<img src="https://img.shields.io/badge/GitHub-gizmodata%2Fadbc--driver--gizmosql-blue.svg?logo=Github">](https://github.com/gizmodata/adbc-driver-gizmosql)
[<img src="https://img.shields.io/badge/GitHub-gizmodata%2Fgizmosql--public-blue.svg?logo=Github">](https://github.com/gizmodata/gizmosql-public)
[![adbc-driver-gizmosql-ci](https://github.com/gizmodata/adbc-driver-gizmosql/actions/workflows/ci.yml/badge.svg)](https://github.com/gizmodata/adbc-driver-gizmosql/actions/workflows/ci.yml)
[![Supported Python Versions](https://img.shields.io/pypi/pyversions/adbc-driver-gizmosql)](https://pypi.org/project/adbc-driver-gizmosql/)
[![PyPI version](https://badge.fury.io/py/adbc-driver-gizmosql.svg)](https://badge.fury.io/py/adbc-driver-gizmosql)
[![PyPI Downloads](https://img.shields.io/pypi/dm/adbc-driver-gizmosql.svg)](https://pypi.org/project/adbc-driver-gizmosql/)

## Overview

`adbc-driver-gizmosql` is a lightweight Python wrapper around [`adbc-driver-flightsql`](https://arrow.apache.org/adbc/current/driver/flight_sql.html) that adds GizmoSQL-specific features:

- **OAuth/SSO browser flow** — Authenticate via your identity provider (Google, Okta, etc.) with a single parameter change
- **DBAPI 2.0 interface** — Drop-in replacement for `adbc_driver_flightsql.dbapi`
- **Zero extra dependencies** — OAuth flow uses only Python stdlib; the only dependency is `adbc-driver-flightsql`

## Setup (to run locally)

### Install Python package
You can install `adbc-driver-gizmosql` from PyPi or from source.

### Option 1 - from PyPi
```shell
# Create the virtual environment
python3 -m venv .venv

# Activate the virtual environment
. .venv/bin/activate

pip install adbc-driver-gizmosql
```

### Option 2 - from source - for development
```shell
git clone https://github.com/gizmodata/adbc-driver-gizmosql

cd adbc-driver-gizmosql

# Create the virtual environment
python3 -m venv .venv

# Activate the virtual environment
. .venv/bin/activate

# Upgrade pip, setuptools, and wheel
pip install --upgrade pip setuptools wheel

# Install adbc-driver-gizmosql - in editable mode with dev and test dependencies
pip install --editable ".[dev,test]"
```

## Usage

### Start a GizmoSQL server

First — start a GizmoSQL server in Docker (mounts a small TPC-H database by default):

```bash
docker run --name gizmosql \
           --detach \
           --rm \
           --tty \
           --init \
           --publish 31337:31337 \
           --env TLS_ENABLED="1" \
           --env GIZMOSQL_PASSWORD="gizmosql_password" \
           --env PRINT_QUERIES="1" \
           --pull missing \
           gizmodata/gizmosql:latest
```

### Password authentication

```python
from adbc_driver_gizmosql import dbapi as gizmosql

with gizmosql.connect("grpc+tls://localhost:31337",
                      username="gizmosql_username",
                      password="gizmosql_password",
                      tls_skip_verify=True,
                      ) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT n_nationkey, n_name FROM nation WHERE n_nationkey = ?",
                    parameters=[24])
        table = cur.fetch_arrow_table()
        print(table)
```

### DDL/DML — execute immediately without fetching

GizmoSQL uses a lazy-execution model, so a plain `cursor.execute()` for DDL/DML
requires a subsequent fetch to actually fire the statement on the server.
`execute_update()` bypasses this by calling the server's
`DoPutPreparedStatementUpdate` RPC directly, executing the statement immediately
and returning the number of rows affected:

```python
from adbc_driver_gizmosql import dbapi as gizmosql

with gizmosql.connect("grpc+tls://localhost:31337",
                      username="gizmosql_username",
                      password="gizmosql_password",
                      tls_skip_verify=True,
                      ) as conn:
    with conn.cursor() as cur:
        # DDL — returns -1 (no row count)
        gizmosql.execute_update(cur, "CREATE TABLE t (a INT)")

        # DML — returns the number of rows affected
        rows_affected = gizmosql.execute_update(cur, "INSERT INTO t VALUES (1)")
        print(f"Rows affected: {rows_affected}")
```

### OAuth/SSO authentication

When your GizmoSQL server is configured with OAuth, simply change `auth_type`:

```python
from adbc_driver_gizmosql import dbapi as gizmosql

with gizmosql.connect("grpc+tls://gizmosql.example.com:31337",
                      auth_type="external",
                      tls_skip_verify=True,
                      ) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT CURRENT_USER AS user")
        print(cur.fetch_arrow_table())
```

This will:
1. Auto-discover the OAuth server endpoint
2. Open your browser to the identity provider login page
3. Poll for completion and retrieve the identity token
4. Connect to GizmoSQL using the token via Basic Auth (`username="token"`)

### Advanced: Standalone OAuth token retrieval

```python
from adbc_driver_gizmosql import get_oauth_token

result = get_oauth_token(
    host="gizmosql.example.com",
    port=31339,           # OAuth HTTP port (default)
    tls_skip_verify=True, # Skip TLS cert verification
    timeout=300,          # Seconds to wait for user to complete auth
)

print(f"Token: {result.token}")
print(f"Session: {result.session_uuid}")
```

### Bulk ingest (load Arrow data into a table)

The ADBC `adbc_ingest` method on the cursor lets you load Arrow tables, record
batches, or record batch readers directly into GizmoSQL — no row-by-row INSERT needed:

```python
import pyarrow as pa
from adbc_driver_gizmosql import dbapi as gizmosql

# Build an Arrow table
table = pa.table({
    "id": [1, 2, 3],
    "name": ["Alice", "Bob", "Charlie"],
    "score": [95.0, 87.5, 91.2],
})

with gizmosql.connect("grpc+tls://localhost:31337",
                      username="gizmosql_username",
                      password="gizmosql_password",
                      tls_skip_verify=True,
                      ) as conn:
    with conn.cursor() as cur:
        # Create a new table and insert the data
        cur.adbc_ingest("students", table, mode="create")

        # Verify
        cur.execute("SELECT * FROM students")
        print(cur.fetch_arrow_table())
```

Supported modes: `"create"`, `"append"`, `"replace"`, `"create_append"`.

### Pandas integration

```python
import pandas as pd
from adbc_driver_gizmosql import dbapi as gizmosql

with gizmosql.connect("grpc+tls://localhost:31337",
                      username="gizmosql_username",
                      password="gizmosql_password",
                      tls_skip_verify=True,
                      ) as conn:
    df = pd.read_sql("SELECT * FROM nation ORDER BY n_nationkey", conn)
    print(df)
```

## API Reference

### `dbapi.connect()`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `uri` | `str` | *required* | Flight SQL URI (e.g., `"grpc+tls://host:31337"`) |
| `username` | `str` | `None` | Username for password auth |
| `password` | `str` | `None` | Password for password auth |
| `tls_skip_verify` | `bool` | `False` | Skip TLS cert verification |
| `auth_type` | `str` | `"password"` | `"password"` or `"external"` (OAuth) |
| `oauth_port` | `int` | `31339` | OAuth HTTP server port |
| `oauth_url` | `str` | `None` | Explicit OAuth base URL |
| `oauth_tls_skip_verify` | `bool` | `None` | TLS skip for OAuth (defaults to `tls_skip_verify`) |
| `oauth_timeout` | `int` | `300` | Seconds to wait for OAuth |
| `open_browser` | `bool` | `True` | Auto-open browser for OAuth |
| `db_kwargs` | `dict` | `None` | Extra ADBC database options |
| `conn_kwargs` | `dict` | `None` | Extra ADBC connection options |
| `autocommit` | `bool` | `True` | Enable autocommit |

### `dbapi.execute_update()`

Execute a DDL/DML statement immediately without fetching. Use this instead of `cursor.execute()` for statements that don't return result sets — it fires the statement on the server right away, bypassing GizmoSQL's lazy-execution model.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `cursor` | `Cursor` | *required* | An open DBAPI 2.0 cursor |
| `query` | `str` | *required* | SQL DDL or DML statement to execute |

Returns: `int` — number of rows affected (`-1` when the server does not report a count, e.g. for DDL)

### `get_oauth_token()`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | *required* | GizmoSQL server hostname |
| `port` | `int` | `31339` | OAuth HTTP port |
| `tls_skip_verify` | `bool` | `True` | Skip TLS cert verification |
| `timeout` | `int` | `300` | Seconds to wait |
| `poll_interval` | `float` | `1` | Seconds between polls |
| `open_browser` | `bool` | `True` | Auto-open browser |
| `oauth_url` | `str` | `None` | Explicit OAuth base URL |

Returns: `OAuthResult(token=str, session_uuid=str)`

## How the OAuth flow works

```
Python Client              GizmoSQL OAuth Server         Identity Provider
     |                            |                            |
     +-- GET /oauth/initiate ---->|                            |
     |<-- {uuid, auth_url} -------|                            |
     |                            |                            |
     +-- Open browser to auth_url-|--------------------------->|
     |                            |                            |
     |                            |<-- callback (auth code) ---|
     |                            |-- exchange code for token ->|
     |                            |<-- id_token ---------------|
     |                            |                            |
     +-- GET /oauth/token/{uuid}->|                            |
     |<-- {status: complete,      |                            |
     |     token: <id_token>}     |                            |
     |                            |                            |
     +-- Flight BasicAuth ------->|                            |
     |   user="token"             | (verify token via JWKS,    |
     |   pass=<id_token>          |  issue server JWT)         |
     |<-- Server Bearer token ----|                            |
```

## Handy development commands

### Version management

#### Bump the version of the application - (you must have installed from source with the [dev] extras)
```bash
bumpver update --patch
```
