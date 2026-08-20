"""Shared constants: connection defaults, timeouts, and safety limits.

Limits are picked to keep FMOD Studio responsive and avoid returning
context-eating payloads to the calling model. Raise them carefully — large
project listings are serialized to JSON on the FMOD side and stringified over
the terminal, so a huge query slows both sides.
"""

import os


class Connection:
    # Default Script Server endpoint. FMOD Studio binds 127.0.0.1:3663 once
    # "Enable Script Server" is ticked under Preferences > Interface (it
    # requires a restart and an open project before it binds).
    HOST = "127.0.0.1"
    PORT = 3663

    # Overridable via env so a non-default port, or (rarely) a tunneled host,
    # works without a code change. Mirrors the env-override convention of
    # Reaper-MCP's REAPER_MCP_* variables.
    @classmethod
    def host(cls) -> str:
        return os.environ.get("FMOD_STUDIO_HOST", cls.HOST)

    @classmethod
    def port(cls) -> int:
        try:
            return int(os.environ.get("FMOD_STUDIO_PORT", str(cls.PORT)))
        except ValueError:
            return cls.PORT

    # All server bookkeeping (process mutex, per-parent generation slots, and
    # the command-history audit trail) lives under one per-user temp
    # directory — never inside the repo. FMOD's Script Server accepts a
    # single terminal session, so a real OS-level lock serializes multiple
    # server processes instead of racing on the one socket.
    @staticmethod
    def mutex_dir() -> str:
        import tempfile

        base = os.path.join(tempfile.gettempdir(), "fmod_studio_mcp")
        os.makedirs(base, exist_ok=True)
        return base

    @staticmethod
    def mutex_file() -> str:
        return os.path.join(Connection.mutex_dir(), "ipc.mutex")

    # One JSON file per completed command (pass or fail), for after-the-fact
    # debugging. Swept for entries older than HISTORY_RETENTION_DAYS.
    @staticmethod
    def history_dir() -> str:
        base = os.path.join(Connection.mutex_dir(), "history")
        os.makedirs(base, exist_ok=True)
        return base


class Timeouts:
    CONNECT = 10.0  # TCP connect to the Script Server
    COMMAND = 30.0  # Default timeout for short operations
    LONG_COMMAND = 600.0  # For bank build / audio import / save+build
    IDLE = 0.3  # "read-until-idle" settle window after a result
    LONG_IDLE = 5.0  # Settle window for long commands (builds go quiet
    # while Studio works, then dump the result)
    QUICK_POLL = 0.05  # mutex poll interval — matches Reaper-MCP


HISTORY_RETENTION_DAYS = 30
HISTORY_PARAM_PREVIEW_CHARS = 2000  # cap stored params — a huge batch call
# shouldn't turn the history dir into
# its own version of the data-dump bug

# Max bytes accepted as a single terminal response. An accidental huge dump
# (e.g. a script that stringifies the entire project) shouldn't pin memory.
MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB

# Read-side context-size caps — protect the calling model's context window,
# not FMOD's responsiveness.
MAX_OBJECTS_READ = 500  # `*_get_all` style listing ceilings
MAX_SOUNDS_READ = 1000  # instruments/sounds per event listing

# Write-side hard ceilings for single-call operations, mirroring Reaper-MCP's
# conservative per-call limits. Large batch scripts block Studio's main thread
# while they run — keep any one command small.
MAX_BATCH_CREATE = 100  # events/instruments created per call
MAX_NAME_LENGTH = 200  # FMOD shouldn't accept unbounded names either

# Automation curves: a parameter-driven crossfade is typically a handful of
# points (map parameter -> db), so this cap is generous while keeping a single
# batch small enough not to pin Studio's main thread.
MAX_AUTOMATION_POINTS = 100

# A wrong type name alerts immediately rather than creating a broken object.
ALLOWED_CREATE_TYPES = frozenset(
    {
        "Event",
        "EventFolder",
        "AssetFolder",
        "Bank",
        "MixerGroup",
        "MixerVCA",
        "Snapshot",
        "Preset",
        "Parameter",
        "GameParameterSetup",
        "SingleSound",
        "MultiSound",
        "ProgrammerSound",
        "SoundScatterer",
        "GroupTrack",
        "Modulator",
        "AutomationCurve",
        "MixerEffect",
        "Relationship",
    }
)
