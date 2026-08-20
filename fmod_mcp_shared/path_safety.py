"""Shared file-path validation — blocks path traversal and system directories.

Used by every tool that reads a file at an AI-supplied path (currently just
audio_import). Mirrors Reaper-MCP's reaper_mcp_shared/path_safety.py so every
sibling MCP server in this family gives the same protection to path-taking
tools instead of leaving it to each tool's own ad hoc checks.
"""
import os
import sys

from fmod_mcp_shared.error_codes import FmodMCPError, ErrorCode

# Directories that should never be accessed
_BLOCKED_DIRS_WIN = [
    os.environ.get("SYSTEMROOT", r"C:\Windows"),
    os.environ.get("SYSTEMDRIVE", "C:") + os.sep + "Program Files",
    os.environ.get("SYSTEMDRIVE", "C:") + os.sep + "Program Files (x86)",
]
_BLOCKED_DIRS_NIX = [
    "/etc", "/bin", "/sbin", "/usr", "/boot", "/proc", "/sys", "/dev",
    "/System", "/Library",
]


def _is_blocked(resolved: str, blocked: str) -> bool:
    # Resolve the blocked entry through realpath too, not just the input —
    # on macOS /etc, /tmp, and /var are symlinks into /private/..., so an
    # already-realpath'd `resolved` (e.g. "/private/etc/x") would never
    # match a literal "/etc" prefix otherwise, silently defeating the block.
    blocked = os.path.realpath(blocked)
    return resolved == blocked or resolved.startswith(blocked + os.sep)


def safe_path(path: str) -> str:
    """Validate and normalize a file path. Blocks traversal and system directories.

    Checks the *raw* input for both conditions before any resolution, not
    the resolved output: `os.path.realpath()` silently makes a relative path
    absolute (by joining it to the cwd) and collapses `..` segments away as
    part of normalizing, so a check against its output can never observe
    either condition — both would be dead code that never fires.
    """
    if not path:
        raise FmodMCPError(ErrorCode.INVALID_PATH, "Path cannot be empty")
    if not os.path.isabs(path):
        raise FmodMCPError(ErrorCode.INVALID_PATH, "Path must be absolute")
    if ".." in path.replace("\\", "/").split("/"):
        raise FmodMCPError(ErrorCode.INVALID_PATH, "Path traversal not allowed")
    resolved = os.path.realpath(path)
    # Block system directories
    if sys.platform == "win32":
        resolved_lower = resolved.lower()
        for blocked in _BLOCKED_DIRS_WIN:
            if resolved_lower.startswith(blocked.lower()):
                raise FmodMCPError(
                    ErrorCode.INVALID_PATH,
                    f"Access to system directory not allowed: {blocked}",
                )
    else:
        for blocked in _BLOCKED_DIRS_NIX:
            if _is_blocked(resolved, blocked):
                raise FmodMCPError(
                    ErrorCode.INVALID_PATH,
                    f"Access to system directory not allowed: {blocked}",
                )
    return resolved
