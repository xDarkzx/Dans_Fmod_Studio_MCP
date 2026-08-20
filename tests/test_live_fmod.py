"""Optional live-FMOD regression tests for the G/N/P JS helpers.

Skipped automatically unless FMOD Studio's Script Server is actually
reachable with a project open — there is no way to unit-test the *real*
property names FMOD's scripting API exposes (e.g. ManagedObject.id vs a
nonexistent .guid) without a live instance, and a previous version of these
helpers shipped with exactly that mismatch — G() read a .guid property that
doesn't exist, P() read a .path property that doesn't exist instead of
calling the real getPath() method — undetected, because every other test in
this suite uses a stub client that never evaluates the injected JS against a
real FMOD object.

Run these manually (`pytest tests/test_live_fmod.py -v`) with FMOD Studio
open and the Script Server enabled whenever touching
fmod_mcp_shared/protocol.py's _JS_HELPERS.
"""

import asyncio
import socket

import pytest

from fmod_mcp.fmod_client import FmodStudioClient
from fmod_mcp_shared.constants import Connection


def _fmod_reachable() -> bool:
    try:
        with socket.create_connection((Connection.host(), Connection.port()), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _fmod_reachable(),
    reason="FMOD Studio's Script Server is not reachable — these tests need a live instance",
)


def test_g_n_p_helpers_against_a_real_project_object():
    """G()/N()/P() must return real, non-null values for an object that
    actually exists, and the returned guid must round-trip through L().
    """

    async def run():
        client = FmodStudioClient()
        r = await client.execute(
            "var arr=studio.project.model.Event.findInstances()||[];"
            "if(arr.length===0)throw new Error('project has no events to test against');"
            "var e=arr[0];"
            "return {guid:G(e),name:N(e),path:P(e)};"
        )
        result = r["result"]
        assert result["guid"] is not None
        assert result["guid"].startswith("{") and result["guid"].endswith("}")
        assert result["name"]
        assert result["path"] is not None
        assert result["path"].startswith("event:/")

        r2 = await client.execute(
            "var e=L(p.target);return {guid:G(e)};", target=result["guid"]
        )
        assert r2["result"]["guid"] == result["guid"]

    asyncio.run(run())


def test_workspace_roots_are_not_null():
    """Regression test for the reported 'workspace roots are all null' bug —
    same root cause as the guid mismatch above (workspace_info runs G() on
    masterEventFolder/masterAssetFolder/masterBus).
    """

    async def run():
        client = FmodStudioClient()
        r = await client.execute(
            "var w=studio.project.workspace;"
            "return {masterEventFolder:G(w.masterEventFolder),"
            "masterAssetFolder:G(w.masterAssetFolder),"
            "masterBus:G(w.mixer.masterBus)};"
        )
        result = r["result"]
        assert result["masterEventFolder"] is not None
        assert result["masterAssetFolder"] is not None
        assert result["masterBus"] is not None

    asyncio.run(run())
