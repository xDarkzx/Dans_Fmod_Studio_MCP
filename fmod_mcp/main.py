import ctypes
import os
import sys
import threading
import time

# MCP's stdio transport requires UTF-8 JSON-RPC framing, but Python's default
# stdio encoding follows the OS/locale's default codepage unless told
# otherwise — on Windows that's a legacy ANSI codepage (cp1252), never UTF-8
# unless the system has opted into "Use Unicode UTF-8 for worldwide language
# support" (off by default). Tool docstrings throughout this codebase use
# non-ASCII characters — under a non-UTF-8 encoding those raise
# UnicodeEncodeError the instant they're written to stdout, which kills the
# whole process. tools/list (sending every registered tool's description) is
# one of the first things every client does on connect, so this crashed the
# server on effectively every session start on an affected system. Applied
# unconditionally — a no-op on a system that's already UTF-8 — and must
# happen before anything touches stdio.
for _stream in (sys.stdout, sys.stdin, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        _reconfigure(encoding="utf-8")

from mcp.server.fastmcp import FastMCP

from fmod_mcp.fmod_client import FmodStudioClient
from fmod_mcp.instructions import load_instructions
from fmod_mcp.tool_registry import register_all_tools
from fmod_mcp_shared.constants import Connection

mcp = FastMCP("FmodStudioMCP", instructions=load_instructions())
client = FmodStudioClient()

register_all_tools(mcp)


def _generation_file(ppid: int) -> str:
    return os.path.join(Connection.mutex_dir(), f"{ppid}.pid")


def _claim_generation(ppid: int) -> None:
    """Register this process as the current server for `ppid`.

    Purely self-descriptive — this never touches another process. Every
    server for the same parent client writes its own PID here on startup;
    whichever wrote last "wins" the slot. Best-effort: if this fails for any
    reason, this server just never sees itself superseded via this path and
    falls back to the parent-liveness watchdog alone, which is safe.
    """
    try:
        os.makedirs(Connection.mutex_dir(), exist_ok=True)
        path = _generation_file(ppid)
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w") as f:
            f.write(str(os.getpid()))
        os.replace(tmp, path)  # atomic — readers never see a torn write
    except OSError:
        pass


def supersede_enabled(env: dict | None = None) -> bool:
    """Whether the "a newer server took over" self-retirement path is active.

    Set FMOD_STUDIO_MCP_NO_SUPERSEDE=1 to switch it off. Needed for clients
    that open more than one connection under a single parent process: the
    generation slot is keyed by parent PID, so a second concurrent connection
    from the same client looks identical to that client having reconnected,
    and the first server retires while its connection is still in active use.
    Same rationale and fix as Reaper-MCP.
    """
    if env is None:
        env = os.environ
    return env.get("FMOD_STUDIO_MCP_NO_SUPERSEDE", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    )


def _superseded(ppid: int) -> bool:
    """True once a newer server has claimed this parent's generation slot.

    Written via atomic replace, so a read here is never torn — accessible the
    moment it differs, no debounce needed. On any read failure, fail safe:
    assume NOT superseded (keep running rather than guessing itself away).
    """
    try:
        with open(_generation_file(ppid)) as f:
            current = int(f.read().strip())
    except (OSError, ValueError):
        return False
    return current != os.getpid()


def _parent_alive(ppid: int) -> bool:
    """Best-effort liveness check. MUST fail open (assume alive) whenever the
    check itself is inconclusive — this feeds a self-termination decision, so
    a false "dead" is far worse than a missed "actually dead".
    """
    if sys.platform == "win32":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, ppid
        )
        if not handle:
            return True
        try:
            # WAIT_OBJECT_0 (0) means the process handle is signaled, i.e. exited
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) != 0
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    else:
        return os.getppid() == ppid


def _watch_parent(poll_seconds: float = 3.0, confirmations_required: int = 3) -> None:
    """Exit this process once it's no longer needed — self-directed only.

    Two independent reasons to retire:
    1. Superseded: the same parent client started a newer server for itself.
    2. Orphaned: the parent client process itself is gone (belt-and-braces
       alongside stdio EOF detection). Requires several consecutive "dead"
       readings so a transient OS-level blip isn't enough to exit.
    """
    ppid = os.getppid()
    consecutive_dead = 0
    check_superseded = supersede_enabled()
    while True:
        time.sleep(poll_seconds)
        if check_superseded and _superseded(ppid):
            os._exit(0)
        if _parent_alive(ppid):
            consecutive_dead = 0
            continue
        consecutive_dead += 1
        if consecutive_dead >= confirmations_required:
            os._exit(0)


def main():
    _claim_generation(os.getppid())
    threading.Thread(target=_watch_parent, daemon=True).start()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
