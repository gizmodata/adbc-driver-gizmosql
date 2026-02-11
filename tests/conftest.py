"""Shared test fixtures for adbc-driver-gizmosql.

Provides a session-scoped Docker fixture that starts a GizmoSQL server
for integration tests. Unit tests do not require Docker.
"""

from __future__ import annotations

import time

import pytest

GIZMOSQL_PORT = 31337
GIZMOSQL_IMAGE = "gizmodata/gizmosql:latest"
GIZMOSQL_USERNAME = "gizmosql_username"
GIZMOSQL_PASSWORD = "gizmosql_password"
CONTAINER_NAME = "adbc-driver-gizmosql-test"


def wait_for_container_log(
    container,
    timeout: int = 30,
    poll_interval: float = 1,
    ready_message: str = "GizmoSQL server - started",
) -> bool:
    """Poll container logs until the ready message appears."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        logs = container.logs().decode("utf-8")
        if ready_message in logs:
            return True
        time.sleep(poll_interval)
    raise TimeoutError(
        f"Container did not show '{ready_message}' in logs within {timeout} seconds."
    )


@pytest.fixture(scope="session")
def gizmosql_server():
    """Start a GizmoSQL server in Docker for integration tests."""
    docker = pytest.importorskip("docker")
    client = docker.from_env()

    container = client.containers.run(
        image=GIZMOSQL_IMAGE,
        name=CONTAINER_NAME,
        detach=True,
        remove=True,
        tty=True,
        init=True,
        ports={f"{GIZMOSQL_PORT}/tcp": GIZMOSQL_PORT},
        environment={
            "GIZMOSQL_USERNAME": GIZMOSQL_USERNAME,
            "GIZMOSQL_PASSWORD": GIZMOSQL_PASSWORD,
            "TLS_ENABLED": "1",
            "PRINT_QUERIES": "1",
            "DATABASE_FILENAME": ":memory:",
            "INIT_SQL_COMMANDS": "CALL dbgen(sf=0.01);"
        },
        stdout=True,
        stderr=True,
    )

    try:
        wait_for_container_log(container)
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def gizmosql_uri():
    """Return the Flight SQL URI for the test server."""
    return f"grpc+tls://localhost:{GIZMOSQL_PORT}"
