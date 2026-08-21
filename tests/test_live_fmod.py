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


def test_automation_add_curve_multi_point_does_not_syntax_error():
    """Regression test: automation_add_curve's multi-statement JS body used
    to join semicolon-terminated statements with ',' — producing
    `a;,b;,c;`, a bare comma at statement position, a JS syntax error. This
    only manifests for 2+ points (a single point has nothing to join
    against), so it went undetected through every stub-client test and
    every hand-written manual test in this project's history — the first
    time the real tool function was ever called end-to-end with 3 points,
    it failed with an opaque "Invalid JSON response from FMOD Studio",
    not a normal thrown error. Creates and cleans up its own throwaway
    project objects so it doesn't touch whatever project is actually open.
    """

    class _StubMCP:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def deco(fn):
                self.tools[fn.__name__] = fn
                return fn

            return deco

    async def run():
        from fmod_mcp.tools import automation_tools

        client = FmodStudioClient()
        group = await client.execute(
            "var g=studio.project.create('MixerGroup');"
            "g.name='__test_automation_group';return {guid:G(g)};"
        )
        event = await client.execute(
            "var e=studio.project.create('Event');"
            "e.name='__test_automation_event';return {guid:G(e)};"
        )
        group_guid = group["result"]["guid"]
        event_guid = event["result"]["guid"]
        try:
            await client.execute(
                "var e=L(p.target);var pt=studio.project.parameterType.User;"
                "e.addGameParameter({name:'__TestParam',type:pt,min:0,max:1});"
                "return true;",
                target=event_guid,
            )

            mcp = _StubMCP()
            automation_tools.register(mcp)
            r = await mcp.tools["automation_add_curve"](
                target=group_guid,
                property="volume",
                driver="parameter:/__TestParam",
                points=[[0.0, 0.0], [0.5, -6.0], [1.0, -12.0]],
                driver_type="parameter",
            )
            assert r["success"] is True
            assert r["result"]["points"] == 3

            listing = await mcp.tools["automation_list"](
                target=group_guid, property="volume"
            )
            curves = listing["result"]["curves"]
            assert len(curves) == 1, (
                f"expected exactly 1 curve, got {len(curves)} — "
                "multi-point call fragmented instead of building one curve"
            )
            assert curves[0]["points"] == [[0.0, 0.0], [0.5, -6.0], [1.0, -12.0]]
        finally:
            await client.execute(
                "var o=L(p.target);studio.project.deleteObject(o);return true;",
                target=group_guid,
            )
            await client.execute(
                "var o=L(p.target);studio.project.deleteObject(o);return true;",
                target=event_guid,
            )

    asyncio.run(run())


def test_marker_add_transition_timeline_produces_valid_objects():
    """marker_add_transition_timeline must produce a TransitionTimeline plus
    source/destination sounds that are actually valid — a
    TransitionSourceSound/TransitionDestinationSound requires both its
    audioTrack and parameter relationships set or FMOD reports isValid:
    false (confirmed live: creating one without them does exactly that).
    Creates and cleans up its own throwaway event/track/markers.
    """

    class _StubMCP:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def deco(fn):
                self.tools[fn.__name__] = fn
                return fn

            return deco

    async def run():
        from fmod_mcp.tools import marker_tools

        client = FmodStudioClient()
        event = await client.execute(
            "var e=studio.project.create('Event');"
            "e.name='__test_transition_timeline_event';return {guid:G(e)};"
        )
        event_guid = event["result"]["guid"]
        try:
            tr = await client.execute(
                "var e=L(p.target);var t=e.addGroupTrack();return {trackGuid:G(t)};",
                target=event_guid,
            )
            track_guid = tr["result"]["trackGuid"]

            mcp = _StubMCP()
            marker_tools.register(mcp)

            mt = await mcp.tools["event_add_marker_track"](target=event_guid)
            marker_track_guid = mt["result"]["guid"]
            dest = await mcp.tools["marker_add_named"](
                track_target=marker_track_guid, name="start", position=0.0
            )
            dest_guid = dest["result"]["guid"]
            tm = await mcp.tools["marker_add_transition"](
                track_target=marker_track_guid,
                position=8.0,
                destination_target=dest_guid,
            )
            tm_guid = tm["result"]["guid"]

            r = await mcp.tools["marker_add_transition_timeline"](
                transition_target=tm_guid,
                audio_track_target=track_guid,
                crossfade_length=1.5,
            )
            assert r["success"] is True
            result = r["result"]
            assert result["transitionTimelineGuid"]
            assert result["sourceGuid"]
            assert result["destinationGuid"]

            # Independently confirm both are actually valid, not just that
            # the call didn't throw.
            check = await client.execute(
                "var s=L(p.src);var d=L(p.dst);"
                "return {sourceValid:s.isValid,destinationValid:d.isValid};",
                src=result["sourceGuid"],
                dst=result["destinationGuid"],
            )
            assert check["result"]["sourceValid"] is True
            assert check["result"]["destinationValid"] is True
        finally:
            await client.execute(
                "var o=L(p.target);studio.project.deleteObject(o);return true;",
                target=event_guid,
            )

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
