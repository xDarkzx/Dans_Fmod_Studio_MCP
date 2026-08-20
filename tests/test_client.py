import asyncio
import socket

import pytest

from fmod_mcp.fmod_client import FmodStudioClient
from fmod_mcp_shared.error_codes import ErrorCode, FmodMCPError


class _FakeSocket:
    """Scriptable socket stand-in that drains a scripted byte buffer."""

    def __init__(self, chunks=None):
        chunks = list(chunks or [])
        chunks.append(b"")  # EOF sentinel after the scripted reads
        self._chunks = iter(chunks)
        self.sent = b""

    def sendall(self, data):
        self.sent += data

    def recv(self, _n):
        try:
            return next(self._chunks)
        except StopIteration:
            raise socket.timeout

    def settimeout(self, _t):
        pass

    def close(self):
        pass


def _patch_socket(monkeypatch, chunks):
    """Make the client serve everything from the scripted fake socket.

    One shared socket instance per patched client so `_connect()` (which each
    round-trip calls again) and the test observe the same `sent` buffer.
    """
    holder = {}
    holder["sock"] = _FakeSocket(chunks)
    monkeypatch.setattr(
        FmodStudioClient,
        "_connect",
        staticmethod(lambda: holder["sock"]),
    )
    return holder["sock"]


def test_roundtrip_parses_result(monkeypatch):
    _patch_socket(monkeypatch, [b'{"success":true,"result":5}'])
    c = FmodStudioClient()
    result = c._roundtrip("return 5;", timeout=5.0, idle=0.05)
    assert result == {"success": True, "result": 5}


def test_roundtrip_sends_wrapped_payload(monkeypatch):
    sock = _patch_socket(monkeypatch, [b'{"success":true,"result":1}'])
    c = FmodStudioClient()
    asyncio.run(c.execute("return p.x;", x=1))
    assert sock.sent.startswith(b"(function(){const p=")
    assert sock.sent.endswith(b"\n")


def test_roundtrip_handles_terminal_noise(monkeypatch):
    _patch_socket(
        monkeypatch, [b"console noise\n", b'{"success":true,"result":{"guid":"{abc}"}}']
    )
    c = FmodStudioClient()
    result = c._roundtrip("x", 5.0, 0.02)
    assert result == {"success": True, "result": {"guid": "{abc}"}}


def test_roundtrip_eof_is_empty_response(monkeypatch):
    _patch_socket(monkeypatch, [])
    c = FmodStudioClient()
    result = c._roundtrip("x", 5.0, 0.02)
    assert result["success"] is False
    assert "Empty response" in result["error"]


def test_roundtrip_forwards_studio_error(monkeypatch):
    _patch_socket(monkeypatch, [b'{"success":false,"error":"boom"}'])
    c = FmodStudioClient()
    result = c._roundtrip("x", 5.0, 0.02)
    assert result == {"success": False, "error": "boom"}


def test_connection_refused_maps_to_typed_error(monkeypatch):
    def refused():
        raise FmodMCPError(ErrorCode.CONNECTION_REFUSED, "cannot reach")

    monkeypatch.setattr(FmodStudioClient, "_connect", staticmethod(refused))
    c = FmodStudioClient()
    with pytest.raises(FmodMCPError) as ei:
        c._roundtrip("x", 5.0, 0.02)
    assert ei.value.code == ErrorCode.CONNECTION_REFUSED


def test_custom_host_port_env(monkeypatch):
    from fmod_mcp_shared.constants import Connection

    monkeypatch.setenv("FMOD_STUDIO_HOST", "10.0.0.9")
    monkeypatch.setenv("FMOD_STUDIO_PORT", "3999")
    assert Connection.host() == "10.0.0.9"
    assert Connection.port() == 3999


def test_execute_round_trips_async(monkeypatch):
    _patch_socket(monkeypatch, [b'{"success":true,"result":{"echo":"Hero"}}'])
    c = FmodStudioClient()
    r = asyncio.run(c.execute("return {echo:p.name};", name="Hero"))
    assert r == {"success": True, "result": {"echo": "Hero"}}


def test_execute_raises_on_studio_error(monkeypatch):
    _patch_socket(monkeypatch, [b'{"success":false,"error":"nope"}'])
    c = FmodStudioClient()
    with pytest.raises(FmodMCPError) as ei:
        asyncio.run(c.execute("studio.project.nothing();"))
    assert ei.value.code == ErrorCode.COMMAND_FAILED
    assert "nope" in ei.value.message
