from mcp.server.fastmcp import FastMCP

from fmod_mcp.safety import ensure_backup
from fmod_mcp_shared.constants import MAX_OBJECTS_READ
from fmod_mcp_shared.error_codes import FmodMCPError, ErrorCode

# Model classes safe to enumerate generically. `studio.project.model.<T>` is
# the class registry; findInstances() returns every instance of that type.
ALLOWED_LIST_TYPES = {
    "Event",
    "Bank",
    "MixerGroup",
    "MixerBus",
    "MixerVCA",
    "Snapshot",
    "Folder",
    "Preset",
}


def register(mcp: FastMCP):
    from fmod_mcp.main import client

    @mcp.tool()
    async def utility_lookup(target: str) -> dict:
        """Resolve any object (event, bank, group, asset, ...) to its identity.

        Args:
            target: Path (event:/..., bank:/...) or {guid}.
        """
        return await client.execute(
            "var o=L(p.target);return {guid:G(o),name:N(o),path:P(o)};", target=target
        )

    @mcp.tool()
    async def utility_list(obj_type: str) -> dict:
        """List every object of a given type (capped).

        Args:
            obj_type: Event | Bank | MixerGroup | MixerBus | MixerVCA |
                      Snapshot | Folder | Preset.
        """
        if obj_type not in ALLOWED_LIST_TYPES:
            raise FmodMCPError(ErrorCode.INVALID_TYPE, f"invalid obj_type {obj_type!r}")
        return await client.execute(
            "var cls=studio.project.model[p.obj_type];"
            "if(!cls||!(cls.findInstances))throw new Error('No model class '+p.obj_type);"
            "var arr=cls.findInstances()||[];"
            "var out=[];"
            "for(var i=0;i<arr.length&&i<{cap};i++){{"
            "out.push({{guid:G(arr[i]),name:N(arr[i]),path:P(arr[i])}});}}"
            "return out;".format(cap=MAX_OBJECTS_READ),
            obj_type=obj_type,
        )

    @mcp.tool()
    async def utility_is_valid(target: str) -> dict:
        """Check whether an object is valid (survived recent edits).

        Args:
            target: Object path or {guid}.
        """
        return await client.execute(
            "var o=L(p.target);return {valid:!!(o.isValid)};",
            target=target,
        )

    @mcp.tool()
    async def utility_delete(target: str) -> dict:
        """Delete any object from the project.

        Warning: destructive and not undoable from the terminal.

        Args:
            target: Object path or {guid}.
        """
        await ensure_backup(client)
        return await client.execute(
            "var o=L(p.target);studio.project.deleteObject(o);return true;",
            target=target,
        )

    @mcp.tool()
    async def utility_dump(target: str) -> dict:
        """Real introspection: every plain property (with value) + every
        relationship (cardinality + count) on a live object. Use this BEFORE
        concluding a capability "doesn't exist" — FMOD's docs only list
        methods, not plain properties (e.g. `looping`), and FMOD's own
        `dump()` only logs to Studio's console and returns nothing here.

        Args:
            target: Object path or {guid}.
        """
        return await client.execute(
            "var o=L(p.target);"
            "var props=[];"
            "for(var k in o){"
            "if(k.charAt(0)==='_')continue;"
            "var v;try{v=o[k];}catch(__e){continue;}"
            "var t=typeof v;if(t==='function'||t==='object')continue;"
            "props.push({name:k,type:t,value:v});}"
            "var rels=[];"
            "for(var k in o.relationships){"
            "var r;try{r=o.relationships[k];}catch(__e){continue;}"
            "if(!r||typeof r!=='object')continue;"
            "var count=(r.destinations)?r.destinations.length:null;"
            "rels.push({name:k,cardinality:r.cardinality||null,count:count});}"
            "return {entity:o.entity,properties:props,relationships:rels};",
            target=target,
        )

    @mcp.tool()
    async def utility_validate() -> dict:
        """Run the project's validation and report issues."""
        return await client.execute(
            "var r=null;"
            "try{r=studio.project.validate();}catch(__e){r=String(__e);}"
            "return {result:r};"
        )
