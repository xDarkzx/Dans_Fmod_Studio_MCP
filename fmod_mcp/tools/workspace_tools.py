from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP):
    from fmod_mcp.main import client

    @mcp.tool()
    async def workspace_info() -> dict:
        """Get the workspace's key roots: event/asset/bank roots and the master bus."""
        return await client.execute(
            "var w=studio.project.workspace;"
            "return {"
            "masterEventFolder:G(w.masterEventFolder),"
            "masterAssetFolder:G(w.masterAssetFolder),"
            "masterBankFolder:G(w.masterBankFolder||null),"
            "masterBus:G(w.mixer.masterBus)"
            "};"
        )

    @mcp.tool()
    async def workspace_browser_current() -> dict:
        """Get the object currently selected in the project browser."""
        return await client.execute(
            "var o=studio.window.browserCurrent();"
            "return o?{guid:G(o),name:N(o),path:P(o)}:null;"
        )

    @mcp.tool()
    async def workspace_navigate(target: str) -> dict:
        """Open an object in the relevant editor (event editor, mixer, ...).

        Args:
            target: Object path or {guid}.
        """
        return await client.execute(
            "var o=L(p.target);studio.window.navigateTo(o);return true;", target=target
        )

    @mcp.tool()
    async def workspace_editor_selection() -> dict:
        """Get the object currently selected in the open editor window."""
        return await client.execute(
            "var o=studio.window.editorSelection();"
            "return o?{guid:G(o),name:N(o),path:P(o)}:null;"
        )
