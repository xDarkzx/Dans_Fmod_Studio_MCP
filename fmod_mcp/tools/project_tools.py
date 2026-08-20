from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP):
    from fmod_mcp.main import client

    @mcp.tool()
    async def project_get_info() -> dict:
        """Get the open project's file path and display name."""
        return await client.execute(
            "return {filePath: studio.project.filePath, name: N(studio.project)};"
        )

    @mcp.tool()
    async def project_save() -> dict:
        """Save the open FMOD Studio project (the active .fspro)."""
        return await client.execute("studio.project.save(); return true;")

    @mcp.tool()
    async def project_save_all() -> dict:
        """Save the project and every edited file (assets, banks, plugins)."""
        return await client.execute("studio.project.saveAll(); return true;")

    @mcp.tool()
    async def project_build(
        banks: list[str] | str | None = None,
        platforms: list[str] | str | None = None,
    ) -> dict:
        """Build banks for the selected platform(s), or scope to specific
        banks/platforms (scoping a big project to one bank is much faster).

        Args:
            banks: Bank name or list (default: every bank).
            platforms: Platform name or list (default: every platform).
        """
        if banks is None and platforms is None:
            return await client.execute_long(
                "var ok=studio.project.build();return {success:!!ok};"
            )
        return await client.execute_long(
            "var opts={};"
            "if(p.banks!==null)opts.banks=p.banks;"
            "if(p.platforms!==null)opts.platforms=p.platforms;"
            "var ok=studio.project.build(opts);return {success:!!ok};",
            banks=banks,
            platforms=platforms,
        )

    @mcp.tool()
    async def project_get_modified() -> dict:
        """Check whether the project has unsaved changes."""
        return await client.execute(
            "var m = false;"
            "try { m = !!studio.project.isModified; } catch (__e) {}"
            "return {modified: m};"
        )
