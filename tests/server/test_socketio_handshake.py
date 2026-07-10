"""Tests for the Socket.IO / Engine.IO v3 "accept-and-idle" handshake.

The real Supernote device polls
``GET /socket.io/?sign=...&random=...&EIO=3&transport=websocket&type=<serial>&token=<jwt>``
repeatedly. These tests verify the mounted ``socketio.AsyncServer`` upgrades
that exact style of request when the JWT `token` is valid, rejects it when
the token is missing/invalid, and that `sign`/`random` are ignored entirely.
"""

import aiohttp
import pytest
from aiohttp.test_utils import TestClient


async def test_eio3_handshake_accepted_with_valid_token(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A valid JWT token upgrades the connection and completes Socket.IO connect."""
    token = auth_headers["x-access-token"]
    url = (
        "/socket.io/?sign=abc123&random=def456&EIO=3&transport=websocket"
        f"&type=TESTDEVICE&token={token}"
    )
    async with client.ws_connect(url) as ws:
        open_msg = await ws.receive(timeout=5)
        assert open_msg.type == aiohttp.WSMsgType.TEXT
        # Engine.IO v3 OPEN packet: "0{...}"
        assert open_msg.data.startswith("0")

        await ws.send_str("40")  # Socket.IO CONNECT packet, default namespace
        connect_ack = await ws.receive(timeout=5)
        assert connect_ack.type == aiohttp.WSMsgType.TEXT
        assert connect_ack.data.startswith("40")


async def test_eio3_handshake_rejected_without_token(client: TestClient) -> None:
    """Missing token must reject the handshake (no open unauthenticated relay)."""
    url = "/socket.io/?sign=abc123&random=def456&EIO=3&transport=websocket&type=TESTDEVICE"
    with pytest.raises(aiohttp.WSServerHandshakeError):
        async with client.ws_connect(url):
            pass


async def test_eio3_handshake_rejected_with_invalid_token(client: TestClient) -> None:
    """An invalid/garbage token must reject the handshake."""
    url = (
        "/socket.io/?sign=abc123&random=def456&EIO=3&transport=websocket"
        "&type=TESTDEVICE&token=not-a-real-jwt"
    )
    with pytest.raises(aiohttp.WSServerHandshakeError):
        async with client.ws_connect(url):
            pass


async def test_rest_endpoints_unaffected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Mounting Socket.IO must not affect ordinary REST auth/routing."""
    resp = await client.post("/api/user/query", headers=auth_headers)
    assert resp.status == 200
    data = await resp.json()
    assert data["success"] is True
