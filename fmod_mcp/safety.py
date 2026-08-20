"""Auto-backup safety net for destructive operations.

Before deleting an event, bank, mixer group, snapshot, or arbitrary object,
save the project and copy its directory to a timestamped sibling so prior
work is recoverable — the scripting terminal has no undo, and FMOD Studio's
own undo history is gone if Studio crashes or the mistake gets saved over
before the next manual save. Mirrors Reaper-MCP's reaper_mcp/safety.py.

FMOD Studio projects are file-based: a small `<name>.fspro` pointer file
sits next to a `Metadata/` folder (the actual event/mixer/bank graph, as
text) and an `Assets/` and `Build/` folder. The delete tools this guards
only ever remove things from the project graph, never audio source files or
build output, so the backup skips `Assets`/`Build` to stay fast — it copies
whatever sits in the project's directory except those two, which covers the
`.fspro` file and `Metadata/` on every project layout without hard-coding
folder names that could change between FMOD versions.
"""

import logging
import os
import shutil
import time

logger = logging.getLogger(__name__)

_backed_up_this_session: set[str] = set()


async def ensure_backup(client) -> dict | None:
    """Save and back up the current project once per session, before a
    destructive tool runs.

    No-op if the project has never been saved (nothing on disk to protect
    yet) or was already backed up earlier in this server process's
    lifetime — the snapshot protects what existed *before* the AI started
    working, not every individual delete.

    Never raises: a failed backup logs a warning and returns None rather
    than blocking the caller's actual operation. Refusing to act at all
    because the safety net itself failed would be a worse outcome than
    proceeding without it — FMOD Studio's own undo is still there.
    """
    try:
        info = await client.execute("return {filePath: studio.project.filePath};")
    except Exception as e:
        logger.warning("Could not check project state for auto-backup: %s", e)
        return None

    result = info.get("result") if isinstance(info, dict) else None
    file_path = result.get("filePath") if isinstance(result, dict) else None

    if not file_path:
        return None  # never been saved — nothing on disk to protect
    if file_path in _backed_up_this_session:
        return None  # already have a snapshot from this session

    project_dir = os.path.dirname(file_path)
    if not project_dir or not os.path.isdir(project_dir):
        return None

    try:
        await client.execute("studio.project.save(); return true;")
    except Exception as e:
        logger.warning("Pre-backup save failed, proceeding without a backup: %s", e)
        return None

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = f"{project_dir}.mcp-backup-{timestamp}"

    try:
        shutil.copytree(
            project_dir, backup_dir, ignore=shutil.ignore_patterns("Assets", "Build")
        )
    except OSError as e:
        logger.warning("Auto-backup failed, proceeding without one: %s", e)
        return None

    _backed_up_this_session.add(file_path)
    logger.info("Auto-backed up project to %s before a destructive action", backup_dir)
    return {"backup_path": backup_dir}
