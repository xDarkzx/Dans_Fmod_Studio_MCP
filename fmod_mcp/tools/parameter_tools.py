from mcp.server.fastmcp import FastMCP

from fmod_mcp_shared.constants import MAX_NAME_LENGTH
from fmod_mcp_shared.error_codes import FmodMCPError, ErrorCode

# The FMOD scripting API distinguishes game parameters (set by the game at
# runtime) from the automation curves on a timeline. These are the documented
# `studio.project.parameterType` members.
ALLOWED_PARAM_TYPES = {
    "User",
    "UserEnumeration",
    "Distance",
    "Direction",
    "Elevation",
    "EventConeAngle",
    "EventOrientation",
}


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
    async def parameter_add(
        event_target: str,
        name: str,
        param_type: str = "User",
        min: float = 0.0,
        max: float = 1.0,
    ) -> dict:
        """Add a game parameter to an event. Errors if a parameter with this
        name already exists on the event, rather than creating a duplicate —
        use parameter_set_initial/parameter_list on the existing one instead.

        The parameter is then settable by the game at runtime, or provides an
        automation line target on the event's timeline.

        Args:
            event_target: event:/ path or {guid}.
            name: Parameter name.
            param_type: User | UserEnumeration | Distance | Direction |
                        Elevation | EventConeAngle | EventOrientation.
            min: Minimum value (default 0).
            max: Maximum value (default 1).
        """
        _check_name(name)
        if param_type not in ALLOWED_PARAM_TYPES:
            raise FmodMCPError(
                ErrorCode.INVALID_TYPE, f"invalid param_type {param_type!r}"
            )
        return await client.execute(
            "var e=L(p.event_target);"
            "var existing=(e.getParameterPresets?e.getParameterPresets():[])||[];"
            "function pname(item){var rel=item.relationships&&item.relationships.presetOwner;"
            "var dest=rel?rel.destinations:null;return (dest&&dest[0])?N(dest[0]):null;}"
            "for(var i=0;i<existing.length;i++){"
            "if(pname(existing[i])===p.name){throw new Error("
            "'parameter \\''+p.name+'\\' already exists on this event (guid '+"
            "G(existing[i])+'); use parameter_set_initial to change it or "
            "parameter_list to inspect it instead of creating a duplicate.');}}"
            "var pt=studio.project.parameterType[p.param_type];"
            "if(pt===undefined)throw new Error('Unknown parameter type: '+p.param_type);"
            "var prm=e.addGameParameter({name:p.name,type:pt,min:p.min,max:p.max});"
            "return {guid:G(prm),name:p.name,type:p.param_type};",
            event_target=event_target,
            name=name,
            param_type=param_type,
            min=min,
            max=max,
        )

    @mcp.tool()
    async def parameter_list(event_target: str) -> dict:
        """List an event's game parameters (name + guid). A parameter's name
        lives behind its presetOwner relationship, not a direct property —
        don't read `.name` on the result of getParameterPresets() directly.

        Args:
            event_target: event:/ path or {guid}.
        """
        return await client.execute(
            "var e=L(p.event_target);"
            "var ps=(e.getParameterPresets?e.getParameterPresets():[])||[];"
            "var out=[];"
            "for(var i=0;i<ps.length;i++){"
            "var rel=ps[i].relationships&&ps[i].relationships.presetOwner;"
            "var dest=rel?rel.destinations:null;"
            "out.push({guid:G(ps[i]),name:(dest&&dest[0])?N(dest[0]):null});}"
            "return out;",
            event_target=event_target,
        )

    @mcp.tool()
    async def parameter_set_initial(
        event_target: str, parameter_name: str, value: float
    ) -> dict:
        """Set a game parameter's initial value on an event.

        Args:
            event_target: event:/ path or {guid}.
            parameter_name: Name of the parameter (from parameter_list).
            value: Initial value.
        """
        return await client.execute(
            "var e=L(p.event_target);"
            "var ps=(e.getParameterPresets?e.getParameterPresets():[])||[];"
            "function pname(item){var rel=item.relationships&&item.relationships.presetOwner;"
            "var dest=rel?rel.destinations:null;return (dest&&dest[0])?N(dest[0]):null;}"
            "var found=null;"
            "for(var i=0;i<ps.length;i++){if(pname(ps[i])===p.parameter_name){found=ps[i];break;}}"
            "if(!found)throw new Error('Parameter not found on event: '+p.parameter_name);"
            "found.initialValue=p.value;"
            "return {parameter:p.parameter_name,initialValue:p.value};",
            event_target=event_target,
            parameter_name=parameter_name,
            value=value,
        )

    @mcp.tool()
    async def parameter_set_labels(
        event_target: str, parameter_name: str, labels: list[str]
    ) -> dict:
        """Set enumeration labels on a UserEnumeration parameter.

        Args:
            event_target: event:/ path or {guid}.
            parameter_name: The parameter's name.
            labels: Human-readable labels, in order (e.g. ["Off","Quiet","Loud"]).
        """
        if not labels or not all(isinstance(x, str) and x for x in labels):
            raise FmodMCPError(
                ErrorCode.INVALID_PARAMETER,
                "labels must be a non-empty list of strings",
            )
        return await client.execute(
            "var e=L(p.event_target);"
            "var ps=(e.getParameterPresets?e.getParameterPresets():[])||[];"
            "function pname(item){var rel=item.relationships&&item.relationships.presetOwner;"
            "var dest=rel?rel.destinations:null;return (dest&&dest[0])?N(dest[0]):null;}"
            "var found=null;"
            "for(var i=0;i<ps.length;i++){if(pname(ps[i])===p.parameter_name){found=ps[i];break;}}"
            "if(!found)throw new Error('Parameter not found on event: '+p.parameter_name);"
            "found.enumerationLabels=p.labels;"
            "return {parameter:p.parameter_name,labels:p.labels};",
            event_target=event_target,
            parameter_name=parameter_name,
            labels=labels,
        )
