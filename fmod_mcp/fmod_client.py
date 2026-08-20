import asyncio
import contextlib
import json
import os
import socket
import sys
import time
import uuid

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from fmod_mcp_shared.constants import (
    Connection,
    Timeouts,
    HISTORY_RETENTION_DAYS,
    HISTORY_PARAM_PREVIEW_CHARS,
)
from fmod_mcp_shared.error_codes import FmodMCPError, ErrorCode
from fmod_mcp_shared.protocol import format_command, parse_response

# Diagnostic-only: any command taking longer than this gets a stage-by-stage
# timing breakdown appended to a slow-commands log, so a real slow request from
# a real long-running server can be diagnosed after the fact instead of
# guessed at. Best-effort — a log write never takes down a real command.
_SLOW_THRESHOLD_SECONDS = 1.0
_SLOW_LOG_FILE = os.path.join(os.path.expanduser("~"), ".fmod_studio_mcp_slow.log")


def _log_slow(command: str, stages: dict) -> None:
    if stages.get("total", 0) < _SLOW_THRESHOLD_SECONDS:
        return
    try:
        parts = " ".join(
            f"{k}={v}" if isinstance(v, int) else f"{k}={v:.2f}s"
            for k, v in stages.items()
        )
        with open(_SLOW_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} "
                f"cmd={command} {parts}\n"
            )
    except OSError:
        pass


def _sweep_history(max_age_days: float = HISTORY_RETENTION_DAYS) -> None:
    """Delete archived command entries older than max_age_days. Best-effort."""
    try:
        cutoff = time.time() - max_age_days * 86400
        with os.scandir(Connection.history_dir()) as it:
            for entry in it:
                try:
                    if entry.is_file() and entry.stat().st_mtime < cutoff:
                        os.remove(entry.path)
                except OSError:
                    continue
    except FileNotFoundError:
        pass
    except Exception:  # noqa: S110
        pass  # best-effort cleanup — never let this disrupt a real command


def _archive_command(
    command: str, params: dict, success: bool, detail, duration: float
) -> None:
    """Write one record of a completed command for after-the-fact review.

    The terminal reply is consumed immediately after each round-trip, so
    without this there's no record of what was sent once it's done. Best
    effort: a failure here must never take down the command it's archiving.
    """
    try:
        hdir = Connection.history_dir()
        os.makedirs(hdir, exist_ok=True)
        params_json = json.dumps(params, default=str)
        truncated = len(params_json) > HISTORY_PARAM_PREVIEW_CHARS
        if truncated:
            params_json = params_json[:HISTORY_PARAM_PREVIEW_CHARS]
        record = {
            "id": str(uuid.uuid4()),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "pid": os.getpid(),
            "command": command,
            "params_preview": params_json,
            "params_truncated": truncated,
            "success": success,
            "duration_sec": round(duration, 3),
        }
        if success:
            record["result_preview"] = json.dumps(detail, default=str)[
                :HISTORY_PARAM_PREVIEW_CHARS
            ]
        else:
            record["error"] = str(detail)

        # Sortable-by-name filename doubles as a unique ID without needing to
        # read the file first.
        fname = f"{time.time():.6f}_{record['id'][:8]}.json"
        path = os.path.join(hdir, fname)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f)
        os.replace(tmp, path)

        _sweep_history()
    except Exception:  # noqa: S110 — best-effort archive; never disrupt the command
        pass


@contextlib.contextmanager
def _ipc_mutex(timeout: float):
    """Real OS-level mutual exclusion for one full command round-trip.

    FMOD's Script Server serves one terminal session; if two fmod-studio-mcp
    server processes (e.g. two separate Claude clients) both send at once,
    their evals would interleave and the response framing would corrupt. A
    real OS lock means the second process just waits its turn instead.
    Non-blocking polling loop so we can respect the caller's timeout budget
    and raise a typed error instead of hanging.
    """
    fd = open(Connection.mutex_file(), "a+b")
    try:
        fd.seek(0, os.SEEK_END)
        if fd.tell() == 0:
            fd.write(b"\0")
            fd.flush()

        deadline = time.monotonic() + timeout
        while True:
            fd.seek(0)
            try:
                if sys.platform == "win32":
                    msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise FmodMCPError(
                        ErrorCode.COMMAND_TIMEOUT,
                        "Timed out waiting for another in-flight FMOD command "
                        "(from this or another fmod-studio-mcp server) to finish.",
                    )
                time.sleep(Timeouts.QUICK_POLL)
        try:
            yield
        finally:
            fd.seek(0)
            try:
                if sys.platform == "win32":
                    msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        fd.close()


class FmodStudioClient:
    def __init__(self):
        self._lock = asyncio.Lock()
        _sweep_history()

    # -- socket helpers ----------------------------------------------------

    @staticmethod
    def _connect() -> socket.socket:
        """Open a fresh connection to the FMOD Script Server and type the error."""
        host, port = Connection.host(), Connection.port()
        try:
            sock = socket.create_connection((host, port), timeout=Timeouts.CONNECT)
        except (socket.timeout, TimeoutError):
            raise FmodMCPError(
                ErrorCode.CONNECTION_TIMEOUT,
                f"Timed out connecting to FMOD Studio's Script Server "
                f"at {host}:{port}.",
            )
        except OSError as e:
            raise FmodMCPError(
                ErrorCode.CONNECTION_REFUSED,
                f"Cannot reach FMOD Studio's scripting terminal at {host}:{port}. "
                f"Ensure FMOD Studio is running with a project open, and the "
                f"Script Server is enabled (Preferences > Interface > Script "
                f"Server, tick 'Enable Script Server' then restart). Detail: {e}",
            )
        return sock

    @staticmethod
    def _read_until_idle(sock: socket.socket, timeout: float, idle: float) -> bytes:
        """Read the terminal's reply using read-until-idle framing.

        The Script Server sends no prompt and no EOF marker — it writes the
        evaluated result as a UTF-8 string and goes quiet. So: accumulate
        everything, and once the socket has been silent for `idle` seconds,
        treat the buffer as the complete response. Long commands (bank build,
        audio import) legitimately go silent while Studio works, which is why
        their idle window is much bigger than a normal command's.
        """
        sock.settimeout(idle)
        deadline = time.monotonic() + timeout
        data = b""
        while time.monotonic() < deadline:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break  # idle window elapsed — response is complete
            if not chunk:
                break  # peer closed — terminal went away mid-command
            data += chunk
            if len(data) >= 10 * 1024 * 1024:  # hard ceiling, see constants
                break
        return data

    def _roundtrip(self, command: str, timeout: float, idle: float) -> dict:
        t_start = time.monotonic()
        sock = self._connect()
        t_connected = time.monotonic()
        try:
            payload = (command + "\n").encode("utf-8")
            try:
                sock.sendall(payload)
            except OSError as e:
                raise FmodMCPError(
                    ErrorCode.SEND_FAILED,
                    f"Failed sending command to FMOD Studio: {e}",
                )
            t_sent = time.monotonic()
            raw = self._read_until_idle(
                sock,
                timeout=max(timeout - (t_sent - t_start), 1.0),
                idle=idle,
            )
            t_read = time.monotonic()
        finally:
            try:
                sock.close()
            except OSError:
                pass

        result = parse_response(raw.decode("utf-8", errors="replace"))
        _log_slow(
            command,
            {
                "connect": t_connected - t_start,
                "send": t_sent - t_connected,
                "read": t_read - t_sent,
                "total": t_read - t_start,
            },
        )
        return result

    # -- public API --------------------------------------------------------

    async def _send(
        self, command: str, params: dict, timeout: float, idle: float
    ) -> dict:
        t_start = time.monotonic()
        full = format_command(command, **params)
        try:
            async with self._lock:
                with _ipc_mutex(timeout):
                    result = await asyncio.wait_for(
                        asyncio.get_running_loop().run_in_executor(
                            None,
                            lambda: self._roundtrip(full, timeout, idle),
                        ),
                        timeout=timeout + 5,
                    )
        except asyncio.TimeoutError:
            raise FmodMCPError(
                ErrorCode.COMMAND_TIMEOUT,
                f"Command timed out after {timeout}s waiting for FMOD Studio to respond",
            )
        if not result.get("success", False):
            raise FmodMCPError(
                ErrorCode.COMMAND_FAILED,
                result.get("error", "Unknown error from FMOD Studio"),
            )
        _archive_command(
            command, params, True, result.get("result"), time.monotonic() - t_start
        )
        return result

    async def execute(self, command: str, **params) -> dict:
        """Run a normal command against the FMOD Studio Script Server."""
        return await self._send(command, params, Timeouts.COMMAND, Timeouts.IDLE)

    async def execute_long(self, command: str, **params) -> dict:
        """Run a long-running command (bank build, audio import, save+build)."""
        return await self._send(
            command, params, Timeouts.LONG_COMMAND, Timeouts.LONG_IDLE
        )

    async def close(self):
        pass
