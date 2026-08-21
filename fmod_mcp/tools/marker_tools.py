from mcp.server.fastmcp import FastMCP

from fmod_mcp.safety import ensure_backup
from fmod_mcp_shared.constants import MAX_NAME_LENGTH
from fmod_mcp_shared.error_codes import FmodMCPError, ErrorCode

# FMOD's project.regionLoopMode enum (scripting-api-reference-project.html).
ALLOWED_LOOP_MODES = {"None", "Looping", "Magnet"}

# Entity names for a marker track's child object types
# (scripting-api-reference-project-model-track.html /
# -project-model-triggerable.html). marker_list tries each individually so
# one entity name changing in a future FMOD version drops that one type
# instead of failing the whole listing.
MARKER_ENTITY_TYPES = (
    "NamedMarker",
    "LoopRegion",
    "SustainPoint",
    "TransitionMarker",
    "TransitionRegion",
)


def _check_name(name: str) -> None:
    if not name or not name.strip():
        raise FmodMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "name must not be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise FmodMCPError(
            ErrorCode.VALUE_OUT_OF_RANGE, f"name too long ({MAX_NAME_LENGTH} max)"
        )


def _check_position(position: float) -> None:
    if position < 0:
        raise FmodMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "position must be >= 0")


def _check_length(length: float) -> None:
    if length <= 0:
        raise FmodMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "length must be > 0")


def register(mcp: FastMCP):
    from fmod_mcp.main import client

    @mcp.tool()
    async def event_add_marker_track(target: str) -> dict:
        """Get-or-create a marker (logic) track on an event's timeline.
        Reuses an existing marker track if the event already has one (most
        events only need one) — check event_list_tracks-style state before
        assuming a fresh track is needed; call this and it will tell you
        via `reused`.

        Args:
            target: event:// path or {guid}.
        """
        return await client.execute(
            "var e=L(p.target);"
            "var rel=e.relationships.markerTracks;"
            "var existing=(rel&&rel.destinations)?rel.destinations:[];"
            "if(existing.length>0){return {guid:G(existing[0]),reused:true};}"
            "var t=e.addMarkerTrack();return {guid:G(t),reused:false};",
            target=target,
        )

    @mcp.tool()
    async def marker_add_named(track_target: str, name: str, position: float) -> dict:
        """Add a named (destination) marker — a labeled point on the
        timeline that transition markers/regions elsewhere can jump to.
        Errors if a marker with this name already exists on the track,
        rather than creating a duplicate — use marker_list to check first.

        Args:
            track_target: Marker track {guid} from event_add_marker_track.
            name: Marker name.
            position: Timeline position in seconds (>= 0).
        """
        _check_name(name)
        _check_position(position)
        return await client.execute(
            "var t=L(p.track_target);"
            "var mrel=t.relationships&&t.relationships.markers;"
            "var existing=(mrel&&mrel.destinations)?mrel.destinations:[];"
            "for(var i=0;i<existing.length;i++){"
            "if(N(existing[i])===p.name){throw new Error("
            "'a marker named \\''+p.name+'\\' already exists on this track "
            "(guid '+G(existing[i])+'); use marker_list to inspect it or "
            "marker_set_position to move it instead of creating a duplicate.');}}"
            "var m=t.addNamedMarker(p.name,p.position);"
            "return {guid:G(m),name:N(m)};",
            track_target=track_target,
            name=name,
            position=position,
        )

    @mcp.tool()
    async def marker_add_region(
        track_target: str,
        name: str,
        position: float,
        length: float,
        loop_mode: str = "Looping",
    ) -> dict:
        """Add a destination (loop) region to a marker track — a labeled
        range, e.g. a section transition markers/regions can jump into.
        Errors if a region with this name already exists on the track,
        rather than creating a duplicate.

        Args:
            track_target: Marker track {guid} from event_add_marker_track.
            name: Region name.
            position: Start position in seconds (>= 0).
            length: Region length in seconds (> 0).
            loop_mode: None | Looping | Magnet (default Looping).
        """
        _check_name(name)
        _check_position(position)
        _check_length(length)
        if loop_mode not in ALLOWED_LOOP_MODES:
            raise FmodMCPError(
                ErrorCode.INVALID_TYPE, f"invalid loop_mode {loop_mode!r}"
            )
        return await client.execute(
            "var t=L(p.track_target);"
            "var mrel=t.relationships&&t.relationships.markers;"
            "var existing=(mrel&&mrel.destinations)?mrel.destinations:[];"
            "for(var i=0;i<existing.length;i++){"
            "if(existing[i].entity==='LoopRegion'&&N(existing[i])===p.name){"
            "throw new Error('a region named \\''+p.name+'\\' already exists "
            "on this track (guid '+G(existing[i])+'); use marker_list to "
            "inspect it or marker_set_region to move/resize it instead of "
            "creating a duplicate.');}}"
            "var lm=studio.project.regionLoopMode[p.loop_mode];"
            "var r=t.addRegion(p.position,p.length,p.name,lm);"
            "return {guid:G(r),name:N(r)};",
            track_target=track_target,
            name=name,
            position=position,
            length=length,
            loop_mode=loop_mode,
        )

    @mcp.tool()
    async def marker_add_sustain_point(track_target: str, position: float) -> dict:
        """Add a sustain point — playback holds here until a keyoff command
        (event_key_off) releases it. Used for loop-until-released sounds
        (e.g. a footstep that holds mid-loop until the game says "stop").

        Args:
            track_target: Marker track {guid} from event_add_marker_track.
            position: Timeline position in seconds (>= 0).
        """
        _check_position(position)
        return await client.execute(
            "var t=L(p.track_target);var s=t.addSustainPoint(p.position);"
            "return {guid:G(s)};",
            track_target=track_target,
            position=position,
        )

    @mcp.tool()
    async def marker_add_transition(
        track_target: str, position: float, destination_target: str
    ) -> dict:
        """Add a transition marker — when playback crosses this point, the
        timeline jumps to the given destination.

        Args:
            track_target: Marker track {guid} from event_add_marker_track.
            position: Timeline position in seconds (>= 0).
            destination_target: {guid} of a NamedMarker or LoopRegion (from
                                 marker_add_named / marker_add_region).
        """
        _check_position(position)
        return await client.execute(
            "var t=L(p.track_target);var d=L(p.destination_target);"
            "var m=t.addTransitionMarker(p.position,d);return {guid:G(m)};",
            track_target=track_target,
            position=position,
            destination_target=destination_target,
        )

    @mcp.tool()
    async def marker_add_transition_region(
        track_target: str, position: float, length: float, destination_target: str
    ) -> dict:
        """Add a transition region — while playback is inside this range,
        the timeline jumps to the given destination.

        Args:
            track_target: Marker track {guid} from event_add_marker_track.
            position: Start position in seconds (>= 0).
            length: Region length in seconds (> 0).
            destination_target: {guid} of a NamedMarker or LoopRegion.
        """
        _check_position(position)
        _check_length(length)
        return await client.execute(
            "var t=L(p.track_target);var d=L(p.destination_target);"
            "var r=t.addTransitionRegion(p.position,p.length,d);"
            "return {guid:G(r)};",
            track_target=track_target,
            position=position,
            length=length,
            destination_target=destination_target,
        )

    @mcp.tool()
    async def marker_list(track_target: str) -> dict:
        """List every marker/region/sustain point/transition on a marker
        track (capped at 200), tagged with its marker type.

        Args:
            track_target: Marker track {guid} from event_add_marker_track.
        """
        types_js = ",".join(f"'{t}'" for t in MARKER_ENTITY_TYPES)
        body = (
            f"var t=L(p.track_target);var types=[{types_js}];var out=[];"
            "for(var i=0;i<types.length;i++){"
            "try{"
            "var cls=studio.project.model[types[i]];"
            "if(!cls)continue;"
            "var arr=cls.findInstances({searchContext:t})||[];"
            "for(var j=0;j<arr.length&&out.length<200;j++){"
            "out.push({guid:G(arr[j]),name:N(arr[j]),markerType:types[i]});}"
            "}catch(__e){}}"
            "return out;"
        )
        return await client.execute(body, track_target=track_target)

    @mcp.tool()
    async def marker_rename(target: str, name: str) -> dict:
        """Rename a named marker or region.

        Args:
            target: Marker/region {guid}.
            name: New name.
        """
        _check_name(name)
        return await client.execute(
            "var o=L(p.target);o.name=p.name;return {guid:G(o),name:N(o)};",
            target=target,
            name=name,
        )

    @mcp.tool()
    async def marker_set_position(target: str, position: float) -> dict:
        """Move a point-type marker (named marker, sustain point,
        transition marker) to a new timeline position.

        Args:
            target: Marker {guid}.
            position: New position in seconds (>= 0).
        """
        _check_position(position)
        return await client.execute(
            "var o=L(p.target);o.position=p.position;"
            "return {guid:G(o),position:p.position};",
            target=target,
            position=position,
        )

    @mcp.tool()
    async def marker_set_region(target: str, position: float, length: float) -> dict:
        """Move/resize a region-type marker (loop region, transition
        region).

        Args:
            target: Region {guid}.
            position: New start position in seconds (>= 0).
            length: New length in seconds (> 0).
        """
        _check_position(position)
        _check_length(length)
        return await client.execute(
            "var o=L(p.target);o.position=p.position;o.length=p.length;"
            "return {guid:G(o),position:p.position,length:p.length};",
            target=target,
            position=position,
            length=length,
        )

    @mcp.tool()
    async def marker_delete(target: str) -> dict:
        """Delete a marker/region/sustain point/transition.

        Args:
            target: Marker {guid}.
        """
        await ensure_backup(client)
        return await client.execute(
            "var o=L(p.target);studio.project.deleteObject(o);return true;",
            target=target,
        )

    @mcp.tool()
    async def marker_add_transition_timeline(
        transition_target: str,
        audio_track_target: str,
        crossfade_length: float = 1.0,
    ) -> dict:
        """Add a transition timeline to a transition marker/region/loop
        region/magnet region, with a source+destination sound pair — FMOD's
        "Add Transition Timeline" feature: a crossfaded transition instead
        of a hard jump-cut, the professional technique for a seamless loop.

        Structurally verified live: this produces a valid TransitionTimeline
        plus TransitionSourceSound/TransitionDestinationSound, both correctly
        bound (a TransitionSourceSound/TransitionDestinationSound requires
        both its `audioTrack` and `parameter` relationships set to be valid
        — confirmed by creating one without them and observing `isValid:
        false`) and overlapped by `crossfade_length` seconds, which is what
        makes FMOD blend them as a crossfade rather than play them back to
        back. The exact blend hasn't been audibly verified against a real
        render — audition it in Studio and adjust `crossfade_length` if the
        blend isn't right; there's no scripted way to "listen" from here.

        Args:
            transition_target: TransitionMarker/TransitionRegion/LoopRegion/
                                MagnetRegion {guid} to add the timeline to.
            audio_track_target: The GroupTrack {guid} whose audio is
                                 transitioning — the track being looped, for
                                 a simple single-track loop.
            crossfade_length: Overlap between outgoing and incoming audio,
                              in seconds (default 1.0, must be > 0). Larger
                              = smoother/slower blend.
        """
        _check_length(crossfade_length)
        return await client.execute(
            "var m=L(p.transition_target);"
            "var at=L(p.audio_track_target);"
            "var tt=studio.project.create('TransitionTimeline');"
            "if(!tt)throw new Error('studio.project.create failed for TransitionTimeline');"
            "m.transitionTimeline=tt;"
            "var src=studio.project.create('TransitionSourceSound');"
            "src.audioTrack=at;src.parameter=tt;src.start=0;src.length=p.crossfade_length;"
            "var dst=studio.project.create('TransitionDestinationSound');"
            "dst.audioTrack=at;dst.parameter=tt;dst.start=0;dst.length=p.crossfade_length;"
            "if(!src.isValid||!dst.isValid)throw new Error("
            "'source/destination sound did not become valid — audioTrack '+"
            "'or parameter binding may have failed silently (sourceValid='+"
            "src.isValid+', destinationValid='+dst.isValid+')');"
            "return {transitionTimelineGuid:G(tt),sourceGuid:G(src),"
            "destinationGuid:G(dst)};",
            transition_target=transition_target,
            audio_track_target=audio_track_target,
            crossfade_length=crossfade_length,
        )
