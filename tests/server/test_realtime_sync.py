"""Tests for real-time push sync via Socket.IO (`finishFolderMessage`).

Covers multi-session fan-out to the same account, cross-user room isolation,
and clean disconnect handling. Uses the `python-socketio` `AsyncClient`
(not the server-side `supernote.server.utils.realtime` module) to connect
as a real device/session would.
"""

import asyncio

import jwt
import pytest
import socketio
from aiohttp.test_utils import TestClient

from supernote.server.config import ServerConfig
from supernote.server.services.coordination import SqliteCoordinationService
from supernote.server.services.user import JWT_ALGORITHM

from .conftest import TEST_USERNAME

SECOND_USERNAME = "a@example.com"

POLL_INTERVAL = 0.1
FANOUT_TIMEOUT = 5.0
ISOLATION_TIMEOUT = 1.5


@pytest.fixture
async def second_user_token(
    server_config: ServerConfig,
    coordination_service: SqliteCoordinationService,
    create_test_user: None,
) -> str:
    """Mint a session token for the second test user, mirroring `auth_headers`."""
    secret = server_config.auth.secret_key
    token = jwt.encode({"sub": SECOND_USERNAME}, secret, algorithm=JWT_ALGORITHM)
    session_val = f"{SECOND_USERNAME}|"
    await coordination_service.set_value(f"session:{token}", session_val, ttl=3600)
    return token


async def _connect_client(client: TestClient, token: str) -> tuple[socketio.AsyncClient, list]:
    """Connect a socketio.AsyncClient authenticated with `token`, tracking received events."""
    sio_client = socketio.AsyncClient(logger=False, engineio_logger=False)
    received: list = []

    @sio_client.on("finishFolderMessage")
    def on_finish_folder(data: dict) -> None:
        received.append(data)

    base_url = str(client.make_url(""))
    await sio_client.connect(
        f"{base_url}?token={token}",
        transports=["websocket"],
        socketio_path="socket.io",
    )
    return sio_client, received


async def _wait_for(received: list, count: int, timeout: float) -> None:
    """Poll `received` until it has at least `count` items or timeout elapses."""

    async def _poll() -> None:
        while len(received) < count:
            await asyncio.sleep(POLL_INTERVAL)

    await asyncio.wait_for(_poll(), timeout=timeout)


async def test_multi_session_same_user_fanout(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Two sessions of the same account both receive finishFolderMessage."""
    token = auth_headers["x-access-token"]
    client_a, received_a = await _connect_client(client, token)
    client_b, received_b = await _connect_client(client, token)
    try:
        resp = await client.post(
            "/api/schedule/groups",
            json={"title": "Test Group"},
            headers=auth_headers,
        )
        assert resp.status == 200

        await _wait_for(received_a, 1, FANOUT_TIMEOUT)
        await _wait_for(received_b, 1, FANOUT_TIMEOUT)

        assert len(received_a) == 1
        assert len(received_b) == 1
        for payload in (received_a[0], received_b[0]):
            assert "timestamp" in payload
            assert isinstance(payload["timestamp"], int)
            assert "directoryId" in payload
            assert payload["directoryId"] is None
    finally:
        await client_a.disconnect()
        await client_b.disconnect()


async def test_cross_user_room_isolation(
    client: TestClient,
    auth_headers: dict[str, str],
    second_user_token: str,
) -> None:
    """A different account's socket must not receive another account's events."""
    other_client, other_received = await _connect_client(client, second_user_token)
    try:
        resp = await client.post(
            "/api/schedule/groups",
            json={"title": "Isolation Test Group"},
            headers=auth_headers,
        )
        assert resp.status == 200

        with pytest.raises(asyncio.TimeoutError):
            await _wait_for(other_received, 1, ISOLATION_TIMEOUT)

        assert other_received == []
    finally:
        await other_client.disconnect()


async def test_disconnect_cleanup_does_not_break_fanout(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A disconnected session is cleanly removed; a still-connected sibling keeps working."""
    token = auth_headers["x-access-token"]
    client_a, received_a = await _connect_client(client, token)
    client_b, received_b = await _connect_client(client, token)

    # Sanity check: both receive the first event.
    resp = await client.post(
        "/api/schedule/groups",
        json={"title": "Pre-disconnect Group"},
        headers=auth_headers,
    )
    assert resp.status == 200
    await _wait_for(received_a, 1, FANOUT_TIMEOUT)
    await _wait_for(received_b, 1, FANOUT_TIMEOUT)

    # Disconnect client_a; this must complete cleanly (no server-side exception).
    await client_a.disconnect()

    try:
        resp = await client.post(
            "/api/schedule/groups",
            json={"title": "Post-disconnect Group"},
            headers=auth_headers,
        )
        assert resp.status == 200

        await _wait_for(received_b, 2, FANOUT_TIMEOUT)
        assert len(received_b) == 2

        # The disconnected client never got the second event.
        assert len(received_a) == 1
    finally:
        await client_b.disconnect()
