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


def register(mcp: FastMCP):
    from fmod_mcp.main import client

    @mcp.tool()
    async def bank_create(name: str) -> dict:
        """Create a bank to hold events and sounds.

        Args:
            name: Bank name. Note: the "Master" bank always exists already.
        """
        _check_name(name)
        return await client.execute(
            "var b=studio.project.create('Bank');b.name=p.name;"
            "return {guid:G(b),name:N(b),path:P(b)};",
            name=name,
        )

    @mcp.tool()
    async def bank_list() -> dict:
        """List every bank in the project (capped)."""
        return await client.execute(
            js_list("studio.project.model.Bank.findInstances()", MAX_OBJECTS_READ)
        )

    @mcp.tool()
    async def bank_info(target: str) -> dict:
        """Get a bank's guid, name and path.

        Args:
            target: bank:/ path or {guid}.
        """
        return await client.execute(
            "var b=L(p.target);return {guid:G(b),name:N(b),path:P(b)};", target=target
        )

    @mcp.tool()
    async def bank_rename(target: str, name: str) -> dict:
        """Rename a bank.

        Args:
            target: bank:/ path or {guid}.
            name: New name.
        """
        _check_name(name)
        return await client.execute(
            "var b=L(p.target);b.name=p.name;return {guid:G(b),name:N(b),path:P(b)};",
            target=target,
            name=name,
        )

    @mcp.tool()
    async def bank_delete(target: str) -> dict:
        """Delete a bank and its contents.

        Args:
            target: bank:/ path or {guid}.
        """
        await ensure_backup(client)
        return await client.execute(
            "var b=L(p.target);studio.project.deleteObject(b);return true;",
            target=target,
        )

    @mcp.tool()
    async def bank_add_event(bank_target: str, event_target: str) -> dict:
        """Assign an event to a bank (so it ships with the build).

        Args:
            bank_target: bank:/ path or {guid}.
            event_target: event:/ path or {guid}.
        """
        return await client.execute(
            "var b=L(p.bank_target);var e=L(p.event_target);"
            "e.relationships.banks.add(b);return true;",
            bank_target=bank_target,
            event_target=event_target,
        )

    @mcp.tool()
    async def bank_remove_event(bank_target: str, event_target: str) -> dict:
        """Remove an event from a bank.

        Args:
            bank_target: bank:/ path or {guid}.
            event_target: event:/ path or {guid}.
        """
        return await client.execute(
            "var b=L(p.bank_target);var e=L(p.event_target);"
            "e.relationships.banks.remove(b);return true;",
            bank_target=bank_target,
            event_target=event_target,
        )

    @mcp.tool()
    async def bank_list_events(bank_target: str) -> dict:
        """List the events assigned to a bank (capped).

        Args:
            bank_target: bank:/ path or {guid}.
        """
        expr = (
            "(function(){"
            "var b=L(p.bank_target);"
            "var events=studio.project.model.Event.findInstances()||[];"
            "var out=[];"
            "for(var i=0;i<events.length;i++){"
            "var rel=events[i].relationships.banks;"
            "var arr=(rel&&rel.destinations)?rel.destinations:[];"
            "for(var j=0;j<arr.length;j++){"
            "if(G(arr[j])===G(b)){out.push(events[i]);break;}}}"
            "return out;})()"
        )
        return await client.execute(
            js_list(expr, MAX_OBJECTS_READ), bank_target=bank_target
        )
