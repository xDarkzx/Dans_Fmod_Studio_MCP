from mcp.server.fastmcp import FastMCP

from fmod_mcp.safety import ensure_backup
from fmod_mcp.tools._common import js_list
from fmod_mcp_shared.constants import MAX_NAME_LENGTH, MAX_OBJECTS_READ
from fmod_mcp_shared.error_codes import FmodMCPError, ErrorCode

# Volume is in dB in FMOD Studio's mixer (-80 .. +10).
VOLUME_MIN, VOLUME_MAX = -80.0, 10.0

# Documented effects the effect chain accepts.
ALLOWED_EFFECTS = {
    "ThreeEQEffect",
    "GainEffect",
    "ChannelMixEffect",
    "ChorusEffect",
    "CompressorEffect",
    "ConvolutionReverbEffect",
    "DistortionEffect",
    "DelayEffect",
    "FlangerEffect",
    "LimiterEffect",
    "MultibandEqEffect",
    "PitchShifterEffect",
    "SFXReverbEffect",
    "TransceiverEffect",
    "TremoloEffect",
    "HighpassEffect",
    "HighpassSimpleEffect",
    "LowpassEffect",
    "LowpassSimpleEffect",
    "ParamEqEffect",
    "SpatialiserEffect",
    "ObjectSpatialiserEffect",
    "LoudnessMeter",
    "SendEffect",
}


def _check_name(name: str) -> None:
    if not name or not name.strip():
        raise FmodMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "name must not be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise FmodMCPError(
            ErrorCode.VALUE_OUT_OF_RANGE, f"name too long ({MAX_NAME_LENGTH} max)"
        )


def _check_volume(db: float) -> None:
    if not VOLUME_MIN <= db <= VOLUME_MAX:
        raise FmodMCPError(
            ErrorCode.VALUE_OUT_OF_RANGE,
            f"volume must be {VOLUME_MIN:g}..{VOLUME_MAX:g} dB",
        )


def register(mcp: FastMCP):
    from fmod_mcp.main import client

    @mcp.tool()
    async def mixer_group_create(name: str, output_target: str | None = None) -> dict:
        """Create a mixer group (routed to Master by default).

        Args:
            name: Group name.
            output_target: Optional output bus/group path or {guid}.
        """
        _check_name(name)
        body = "var g=studio.project.create('MixerGroup');g.name=p.name;"
        if output_target:
            body += "g.output=L(p.output_target);"
        body += "return {guid:G(g),name:N(g)};"
        return await client.execute(body, name=name, output_target=output_target)

    @mcp.tool()
    async def mixer_group_list() -> dict:
        """List every mixer group in the project (capped)."""
        return await client.execute(
            js_list("studio.project.model.MixerGroup.findInstances()", MAX_OBJECTS_READ)
        )

    @mcp.tool()
    async def mixer_group_info(target: str) -> dict:
        """Get a mixer group's guid, name, path and current volume (dB).

        Args:
            target: Group path or {guid}.
        """
        return await client.execute(
            "var g=L(p.target);var v=null;"
            "try{v=g.volume;}catch(__e){}"
            "return {guid:G(g),name:N(g),path:P(g),volume:v};",
            target=target,
        )

    @mcp.tool()
    async def mixer_group_rename(target: str, name: str) -> dict:
        """Rename a mixer group.

        Args:
            target: Group path or {guid}.
            name: New name.
        """
        _check_name(name)
        return await client.execute(
            "var g=L(p.target);g.name=p.name;return {guid:G(g),name:N(g)};",
            target=target,
            name=name,
        )

    @mcp.tool()
    async def mixer_group_delete(target: str) -> dict:
        """Delete a mixer group.

        Warning: objects routed through it will need re-routing afterwards.

        Args:
            target: Group path or {guid}.
        """
        await ensure_backup(client)
        return await client.execute(
            "var g=L(p.target);studio.project.deleteObject(g);return true;",
            target=target,
        )

    @mcp.tool()
    async def mixer_group_route(target: str, output_target: str) -> dict:
        """Route a group's output to a bus or group. Keep routing inside the
        same event/mixer surface — routing an event's master track into a
        different event's mixer has been known to crash Studio.

        Args:
            target: Group path or {guid}.
            output_target: Destination bus/group path or {guid}.
        """
        return await client.execute(
            "var g=L(p.target);g.output=L(p.output_target);return true;",
            target=target,
            output_target=output_target,
        )

    @mcp.tool()
    async def mixer_group_volume(target: str, db: float) -> dict:
        """Set a mixer group's volume, in dB (-80 .. +10).

        Args:
            target: Group path or {guid}.
            db: Volume in decibels.
        """
        _check_volume(db)
        return await client.execute(
            "var g=L(p.target);g.volume=p.db;return {guid:G(g),volume:p.db};",
            target=target,
            db=db,
        )

    @mcp.tool()
    async def mixer_effect_add(target: str, effect: str) -> dict:
        """Add an effect to a group's effect chain.

        Args:
            target: Group path or {guid}.
            effect: Effect type, e.g. CompressorEffect, LimiterEffect,
                    ParamEqEffect, LowpassEffect, DelayEffect,
                    ConvolutionReverbEffect, DistortionEffect, ...
        """
        if effect not in ALLOWED_EFFECTS:
            raise FmodMCPError(ErrorCode.INVALID_TYPE, f"invalid effect {effect!r}")
        return await client.execute(
            "var g=L(p.target);var fx=g.effectChain.addEffect(p.effect);return {guid:G(fx)};",
            target=target,
            effect=effect,
        )

    @mcp.tool()
    async def mixer_effect_list(target: str) -> dict:
        """List the effects on a group's chain.

        Args:
            target: Group path or {guid}.
        """
        return await client.execute(
            "var g=L(p.target);"
            "var rel=g.effectChain.relationships.effects;"
            "var arr=(rel&&rel.destinations)?rel.destinations:[];"
            "var out=[];"
            "for(var i=0;i<arr.length&&i<50;i++){"
            "out.push({guid:G(arr[i]),name:N(arr[i]),entity:arr[i].entity});}"
            "return out;",
            target=target,
        )

    @mcp.tool()
    async def mixer_master_info() -> dict:
        """Get the master bus guid, name and volume."""
        return await client.execute(
            "var mb=studio.project.workspace.mixer.masterBus;"
            "return {guid:G(mb),name:N(mb),volume:mb.volume};"
        )

    @mcp.tool()
    async def mixer_master_volume(db: float) -> dict:
        """Set the master bus volume, in dB (-80 .. +10).

        Args:
            db: Volume in decibels.
        """
        _check_volume(db)
        return await client.execute(
            "var mb=studio.project.workspace.mixer.masterBus;mb.volume=p.db;return {volume:p.db};",
            db=db,
        )

    @mcp.tool()
    async def vca_create(name: str) -> dict:
        """Create a VCA (Voltage-Controlled Amplifier) — a volume control
        that scales every mixer strip assigned to it, for grouping several
        buses under one fader (e.g. "Music", "SFX", "Voice").

        Args:
            name: VCA name.
        """
        _check_name(name)
        return await client.execute(
            "var v=studio.project.create('MixerVCA');v.name=p.name;"
            "return {guid:G(v),name:N(v)};",
            name=name,
        )

    @mcp.tool()
    async def vca_list() -> dict:
        """List every VCA in the project (capped)."""
        return await client.execute(
            js_list("studio.project.model.MixerVCA.findInstances()", MAX_OBJECTS_READ)
        )

    @mcp.tool()
    async def vca_info(target: str) -> dict:
        """Get a VCA's guid, name and current volume (dB).

        Args:
            target: vca:/ path or {guid}.
        """
        return await client.execute(
            "var v=L(p.target);var vol=null;try{vol=v.volume;}catch(__e){}"
            "return {guid:G(v),name:N(v),volume:vol};",
            target=target,
        )

    @mcp.tool()
    async def vca_volume(target: str, db: float) -> dict:
        """Set a VCA's volume, in dB (-80 .. +10).

        Args:
            target: vca:/ path or {guid}.
            db: Volume in decibels.
        """
        _check_volume(db)
        return await client.execute(
            "var v=L(p.target);v.volume=p.db;return {guid:G(v),volume:p.db};",
            target=target,
            db=db,
        )

    @mcp.tool()
    async def vca_assign(vca_target: str, strip_target: str) -> dict:
        """Assign a mixer strip (group/bus) to a VCA so the VCA's fader
        scales it alongside every other strip assigned to it.

        FMOD's docs don't name the exact assignment relationship — this
        tries a couple of plausible names and raises a clear error instead
        of silently doing nothing if neither applies.

        Args:
            vca_target: vca:/ path or {guid}.
            strip_target: Mixer group/bus path or {guid} to assign.
        """
        return await client.execute(
            "var v=L(p.vca_target);var s=L(p.strip_target);"
            "var names=['vcas','assignedVCAs'];var done=false;"
            "for(var i=0;i<names.length;i++){"
            "try{if(s.relationships&&s.relationships[names[i]]){"
            "s.relationships[names[i]].add(v);done=true;break;}}catch(__e){}}"
            "if(!done)throw new Error("
            "'Could not find a VCA-assignment relationship on this strip; "
            "inspect it with utility_dump to find the correct relationship name.');"
            "return {vca:G(v),strip:G(s)};",
            vca_target=vca_target,
            strip_target=strip_target,
        )

    @mcp.tool()
    async def mixer_send_create(
        event_target: str,
        source_group_target: str,
        return_name: str,
        level_db: float = 0.0,
    ) -> dict:
        """Create a return track + send within one event's mixer (e.g. a
        shared reverb bus). Per-event only — no cross-event/global send here.

        Args:
            event_target: event:// path or {guid}, owns both the source
                          group and the new return.
            source_group_target: Source mixerGroupGuid to send from.
            return_name: Name for the new return track.
            level_db: Send level in dB (-80..+10, default 0).
        """
        _check_name(return_name)
        _check_volume(level_db)
        return await client.execute(
            "var e=L(p.event_target);var g=L(p.source_group_target);"
            "var ret=e.addReturnTrack(p.return_name);"
            "var fx=g.effectChain.addEffect('SendEffect');"
            "fx.target=ret;"
            "try{fx.level=p.level_db;}catch(__e){}"
            "return {returnGuid:G(ret),returnName:N(ret),sendGuid:G(fx)};",
            event_target=event_target,
            source_group_target=source_group_target,
            return_name=return_name,
            level_db=level_db,
        )
