from mcp.server.fastmcp import FastMCP

from fmod_mcp_shared.constants import MAX_OBJECTS_READ
from fmod_mcp_shared.error_codes import FmodMCPError, ErrorCode

ALLOWED_FOLDER_KINDS = {"EventFolder", "AssetFolder"}


def register(mcp: FastMCP):
    from fmod_mcp.main import client

    @mcp.tool()
    async def folder_create(kind: str, path: str) -> dict:
        """Find-or-create a folder chain (e.g. "UI/HUD" resolves/creates UI
        then HUD) — safe to call repeatedly, reuses existing folders.

        Args:
            kind: EventFolder | AssetFolder. AssetFolder isn't creatable in
                  FMOD Studio 2.03.14 (errors clearly rather than no-op'ing).
            path: Slash-separated, e.g. "UI/HUD".
        """
        if kind not in ALLOWED_FOLDER_KINDS:
            raise FmodMCPError(ErrorCode.INVALID_TYPE, f"invalid folder kind {kind!r}")
        return await client.execute(
            "var kind=p.kind;"
            "var root=kind==='AssetFolder'?"
            "studio.project.workspace.masterAssetFolder:"
            "studio.project.workspace.masterEventFolder;"
            "var segs=(p.path||'').split('/');"
            "var cur=root;"
            "function findChild(f,n){"
            "var rel=f.relationships&&f.relationships.items;"
            "var kids=(rel&&rel.destinations)?rel.destinations:[];"
            "for(var i=0;i<kids.length;i++){"
            "if(kids[i].name===n)return kids[i];}return null;}"
            "for(var i=0;i<segs.length;i++){"
            "var s=segs[i];if(!s)continue;"
            "var child=findChild(cur,s);"
            "if(!child){"
            "child=studio.project.create(kind);"
            "if(!child)throw new Error("
            "'studio.project.create failed for kind: '+kind+"
            "' — this folder kind may not be creatable via scripting in this FMOD version.');"
            "child.name=s;"
            "try{child.folder=cur;}catch(__e){"
            "try{child.parent=cur;}catch(__e2){}}}"
            "cur=child;}"
            "return {guid:G(cur),name:N(cur),path:P(cur)};",
            kind=kind,
            path=path,
        )

    @mcp.tool()
    async def folder_list(kind: str | None = None) -> dict:
        """List folders in the project browser (capped).

        Args:
            kind: Optional filter — EventFolder | AssetFolder. Omit for all.
        """
        # js_list can't filter — inline the cap+filter so the model never
        # floods the reply with folders from both browsers.
        body = (
            "var all=studio.project.model.Folder.findInstances()||[];"
            "var out=[];"
            "for(var i=0;i<all.length&&out.length<{cap};i++){{"
            "var o=all[i];"
            "if(p.kind&&!(o.isOfExactType&&o.isOfExactType(p.kind)))continue;"
            "out.push({{guid:G(o),name:N(o),path:P(o)}});}}"
            "return out;".format(cap=MAX_OBJECTS_READ)
        )
        return await client.execute(body, kind=kind)
