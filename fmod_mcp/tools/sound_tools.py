import os
import struct
import wave

from mcp.server.fastmcp import FastMCP

from fmod_mcp.tools._common import js_list
from fmod_mcp_shared.constants import MAX_NAME_LENGTH
from fmod_mcp_shared.error_codes import FmodMCPError, ErrorCode
from fmod_mcp_shared.path_safety import safe_path

# Supported audio import formats + instrument types. Both validated up front
# so a typo fails fast with a typed error instead of an opaque Studio message.
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".aiff", ".aif", ".flac", ".mp3", ".ogg"}
ALLOWED_SOUND_TYPES = {
    "SingleSound",
    "MultiSound",
    "ProgrammerSound",
    "SoundScatterer",
    "EventSound",
}

# How much of a WAV file to scan for silence. A bad DAW bounce is silent
# throughout, not just at the start, so a bounded prefix is enough — reading
# the whole file would be needless time/memory for a multi-minute asset.
_SILENCE_CHECK_SECONDS = 10.0
_SILENCE_PEAK_THRESHOLD = 0.001  # ~ -60 dBFS


def _check_wav_not_silent(path: str) -> None:
    """Best-effort silence detector for an imported WAV before it's wired
    into an instrument. FMOD Studio's import succeeds, and the instrument
    looks correctly set up, even when the source render was blank — the
    only way to have caught that before this was to listen after the fact.

    Uses only the stdlib `wave` module (no new dependency) against raw PCM
    samples, so it only covers 8/16-bit PCM WAV — the common case for a DAW
    bounce. Anything else (compressed WAV, 24/32-bit, non-WAV formats) is
    skipped silently rather than risk a false positive from misreading it;
    this is a safety net for the common failure mode, not a full audio
    validator.
    """
    try:
        with wave.open(path, "rb") as w:
            framerate = w.getframerate() or 44100
            sampwidth = w.getsampwidth()
            max_frames = int(_SILENCE_CHECK_SECONDS * framerate)
            raw = w.readframes(min(w.getnframes(), max_frames))
    except (wave.Error, EOFError, OSError):
        return  # not a WAV we can safely parse this way — skip, not a failure

    if not raw:
        raise FmodMCPError(
            ErrorCode.INVALID_FORMAT, f"audio file has no sample data: {path}"
        )

    if sampwidth == 2:
        count = len(raw) // 2
        if count == 0:
            return
        samples = struct.unpack(f"<{count}h", raw[: count * 2])
        peak = max(abs(s) for s in samples) / 32768.0
    elif sampwidth == 1:
        samples = raw
        peak = max(abs(b - 128) for b in samples) / 128.0
    else:
        return  # 24/32-bit — skip rather than mis-parse

    if peak < _SILENCE_PEAK_THRESHOLD:
        raise FmodMCPError(
            ErrorCode.INVALID_FORMAT,
            f"audio file appears to be silent (peak level {peak:.4f} over the "
            f"first {_SILENCE_CHECK_SECONDS:g}s, threshold {_SILENCE_PEAK_THRESHOLD:g}): "
            f"{path}. This usually means the source render/bounce was blank — "
            f"re-check it before importing rather than wiring up empty audio.",
        )


def _check_import(path: str) -> str:
    """Validate an audio import path and return its resolved, safe form.

    Blocks traversal/system-directory access via safe_path() (the same guard
    Reaper-MCP applies to every path-taking tool) before checking existence
    and extension — a project has no business importing from outside its own
    asset tree. WAV files also get a best-effort silence check — see
    _check_wav_not_silent.
    """
    resolved = safe_path(path)
    if not os.path.exists(resolved):
        raise FmodMCPError(ErrorCode.INVALID_PATH, f"audio file not found: {resolved}")
    ext = os.path.splitext(resolved)[1].lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise FmodMCPError(
            ErrorCode.INVALID_FORMAT,
            f"unsupported audio format {ext!r}; supported: "
            f"{sorted(ALLOWED_AUDIO_EXTENSIONS)}",
        )
    if ext == ".wav":
        _check_wav_not_silent(resolved)
    return resolved


def register(mcp: FastMCP):
    from fmod_mcp.main import client

    @mcp.tool()
    async def audio_import(file_path: str) -> dict:
        """Import an audio file into the project as a reusable asset.

        Returns the asset's {guid} so it can be assigned to an instrument.
        Long operation — asset files are copied into the project.

        Args:
            file_path: Absolute path to a .wav/.aiff/.flac/.mp3/.ogg file.
        """
        resolved_path = _check_import(file_path)
        return await client.execute_long(
            "var a=studio.project.importAudioFile(p.file_path);"
            "if(!a)throw new Error('Failed to import audio file: '+p.file_path);"
            "return {guid:G(a),name:N(a),path:P(a)};",
            file_path=resolved_path,
        )

    @mcp.tool()
    async def audio_assets() -> dict:
        """List imported audio assets in the project (capped)."""
        return await client.execute_long(
            js_list("studio.project.model.Asset.findInstances()")
        )

    @mcp.tool()
    async def sound_add_to_track(
        event_target: str,
        track_target: str,
        sound_type: str,
        start: float = 0.0,
        length: float = 0.0,
        name: str | None = None,
    ) -> dict:
        """Place an instrument on an event's track timeline. Returned {guid}
        is for follow-up calls (sound_set_audio_file, sound_set_owner).

        Args:
            event_target: event:/ path or {guid}.
            track_target: trackGuid (not mixerGroupGuid) from event_list_tracks.
            sound_type: SingleSound | MultiSound | ProgrammerSound |
                        SoundScatterer | EventSound.
            start: Start position, seconds.
            length: Length in seconds (0 = untrimmed).
            name: Optional instrument name.
        """
        if sound_type not in ALLOWED_SOUND_TYPES:
            raise FmodMCPError(
                ErrorCode.INVALID_TYPE, f"invalid sound_type {sound_type!r}"
            )
        if length < 0:
            raise FmodMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "length must be >= 0")
        body = (
            "var e=L(p.event_target);var t=L(p.track_target);"
            "var inst=t.addSound(e.timeline,p.sound_type,p.start,p.length);"
        )
        if name:
            _check_instrument_name(name)
            body += "inst.name=p.name;"
        body += "return {guid:G(inst),name:N(inst)};"
        return await client.execute(
            body,
            event_target=event_target,
            track_target=track_target,
            sound_type=sound_type,
            start=start,
            length=length,
            name=name,
        )

    @mcp.tool()
    async def sound_create(sound_type: str, name: str | None = None) -> dict:
        """Create a standalone instrument (usually a SingleSound for a Multi's playlist).

        Args:
            sound_type: SingleSound | MultiSound | ProgrammerSound |
                        SoundScatterer | EventSound.
            name: Optional instrument name.
        """
        if sound_type not in ALLOWED_SOUND_TYPES:
            raise FmodMCPError(
                ErrorCode.INVALID_TYPE, f"invalid sound_type {sound_type!r}"
            )
        body = "var s=studio.project.create(p.sound_type);"
        if name:
            _check_instrument_name(name)
            body += "s.name=p.name;"
        body += "return {guid:G(s),name:N(s)};"
        return await client.execute(body, sound_type=sound_type, name=name)

    @mcp.tool()
    async def sound_set_audio_file(target: str, audio: str) -> dict:
        """Assign an imported audio asset to an instrument.

        Reads the assignment back before returning — a `guid` alone isn't
        proof the audio actually attached, only that the JS call didn't
        throw. If `audioFileGuid` comes back null, the assignment silently
        didn't take (this raises instead of reporting a false success).

        Args:
            target: Instrument {guid} or path.
            audio: Asset {guid} from audio_import.
        """
        return await client.execute(
            "var s=L(p.target);var a=L(p.audio);s.audioFile=a;"
            "var af=s.audioFile;"
            "if(!af)throw new Error("
            "'audioFile assignment did not take effect on '+p.target+"
            "' — this instrument type may not support an audioFile relationship.');"
            "return {guid:G(s),audioFileGuid:G(af),audioFileName:N(af)};",
            target=target,
            audio=audio,
        )

    @mcp.tool()
    async def sound_set_owner(target: str, owner: str) -> dict:
        """Set a sound's owning instrument (e.g. a SingleSound into a MultiSound).

        Reads the assignment back before returning — see sound_set_audio_file.

        Args:
            target: SingleSound {guid}.
            owner: Owner MultiSound/Scatterer {guid}.
        """
        return await client.execute(
            "var s=L(p.target);var o=L(p.owner);s.owner=o;"
            "var actual=s.owner;"
            "if(!actual||G(actual)!==G(o))throw new Error("
            "'owner assignment did not take effect on '+p.target+'.');"
            "return {guid:G(s),ownerGuid:G(actual)};",
            target=target,
            owner=owner,
        )

    @mcp.tool()
    async def sound_set_name(target: str, name: str) -> dict:
        """Rename an instrument.

        Args:
            target: Instrument {guid} or path.
            name: New name.
        """
        _check_instrument_name(name)
        return await client.execute(
            "var s=L(p.target);s.name=p.name;return {guid:G(s),name:N(s)};",
            target=target,
            name=name,
        )

    @mcp.tool()
    async def sound_info(target: str) -> dict:
        """Get an instrument's guid, name, path, and whether it actually has
        an audio asset attached (hasAudioFile / audioFileName) — a SingleSound
        with no audio assigned shows an empty box with no waveform in Studio
        and plays silence; check this after sound_set_audio_file rather than
        assuming the assignment stuck.

        Args:
            target: Instrument {guid} or path.
        """
        return await client.execute(
            "var s=L(p.target);var af=s.audioFile;"
            "return {guid:G(s),name:N(s),path:P(s),"
            "hasAudioFile:!!af,"
            "audioFileGuid:af?G(af):null,"
            "audioFileName:af?N(af):null};",
            target=target,
        )


def _check_instrument_name(name: str) -> None:
    if not name or not name.strip():
        raise FmodMCPError(
            ErrorCode.VALUE_OUT_OF_RANGE, "instrument name must not be empty"
        )
    if len(name) > MAX_NAME_LENGTH:
        raise FmodMCPError(
            ErrorCode.VALUE_OUT_OF_RANGE, f"name too long ({MAX_NAME_LENGTH} max)"
        )
