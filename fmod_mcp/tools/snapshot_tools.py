from mcp.server.fastmcp import FastMCP

from fmod_mcp.safety import ensure_backup
from fmod_mcp.tools._common import js_list
from fmod_mcp_shared.constants import MAX_NAME_LENGTH, MAX_OBJECTS_READ
from fmod_mcp_shared.error_codes import FmodMCPError, ErrorCode


def _check_name(name: str) -> None:
    if not name or not name.strip():
        raise FmodMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "name must not be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise FmodMCPError(
            ErrorCode.VALUE_OUT_OF_RANGE, f"name too long ({MAX_NAME_LENGTH} max)"
        )


_SNAPSHOT_FIND = "studio.project.model.Snapshot.findInstances()"


def register(mcp: FastMCP):
    from fmod_mcp.main import client

    @mcp.tool()
    async def snapshot_create(name: str) -> dict:
        """Create a mixer snapshot.

        A snapshot captures a set of mixer state changes (group/bus/VCA
        volumes, effect settings) that the game activates as a blendable
        state — e.g. a 'dungeon' or 'night' reverb/level shift layered over
        the base mix. Mixer settings are captured by Studio when you move a
        control while the snapshot is armed; pass the returned path to
        snapshot_bind_group to pin a group's current settings.

        Args:
            name: Snapshot name.
        """
        _check_name(name)
        return await client.execute(
            "var s=studio.project.create('Snapshot');s.name=p.name;"
            "return {guid:G(s),name:N(s),path:P(s)};",
            name=name,
        )

    @mcp.tool()
    async def snapshot_list() -> dict:
        """List every mixer snapshot in the project (capped)."""
        return await client.execute(js_list(_SNAPSHOT_FIND, MAX_OBJECTS_READ))

    @mcp.tool()
    async def snapshot_info(target: str) -> dict:
        """Get a snapshot's guid, name and path.

        Args:
            target: snapshot:/ path or {guid}.
        """
        return await client.execute(
            "var s=L(p.target);return {guid:G(s),name:N(s),path:P(s)};",
            target=target,
        )

    @mcp.tool()
    async def snapshot_rename(target: str, name: str) -> dict:
        """Rename a mixer snapshot.

        Args:
            target: snapshot:/ path or {guid}.
            name: New name.
        """
        _check_name(name)
        return await client.execute(
            "var s=L(p.target);s.name=p.name;return {guid:G(s),name:N(s)};",
            target=target,
            name=name,
        )

    @mcp.tool()
    async def snapshot_delete(target: str) -> dict:
        """Delete a mixer snapshot.

        Args:
            target: snapshot:/ path or {guid}.
        """
        await ensure_backup(client)
        return await client.execute(
            "var s=L(p.target);studio.project.deleteObject(s);return true;",
            target=target,
        )

    @mcp.tool()
    async def snapshot_bind_group(snapshot_target: str, group_target: str) -> dict:
        """Bind a mixer group's captured settings to a snapshot.

        Snapshots store per-group mixer states. Binding a group to a snapshot
        tells Studio that group owns a setting within it, so later mixer edits
        while the snapshot is armed capture into that snapshot.

        Args:
            snapshot_target: snapshot:/ path or {guid}.
            group_target: bus:/ or mixer group path/{guid}.
        """
        return await client.execute(
            "var s=L(p.snapshot_target);"
            "var g=L(p.group_target);"
            "var binds=s.relationships&&s.relationships.groups?true:false;"
            "if(binds){s.relationships.groups.add(g);}"
            "return {snapshot:N(s)||P(s),group:N(g)||P(g),bound:binds};",
            snapshot_target=snapshot_target,
            group_target=group_target,
        )
