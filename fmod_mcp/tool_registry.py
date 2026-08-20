import importlib
import logging
import os
import pkgutil
import sys

from mcp.server.fastmcp import FastMCP

import fmod_mcp.tools as tools_package

logger = logging.getLogger(__name__)


# Tool-count categories per profile are approximate — the real count is the
# sum of @mcp.tool() registrations in each module's register().
PROFILES: dict[str, set[str] | None] = {
    # `full` — everything. Default. The complete authoring surface.
    "full": None,
    # `events` — build and edit events, sounds and parameters. The core of
    # game-audio authoring; drops mixer, banks, workspace navigation.
    "events": {
        "project_tools",
        "event_tools",
        "sound_tools",
        "parameter_tools",
        "automation_tools",
        "audition_tools",
        "marker_tools",
        "folder_tools",
        "utility_tools",
    },
    # `mixer` — mixer structure, routing, effects, snapshots + minimal project.
    "mixer": {
        "project_tools",
        "mixer_tools",
        "snapshot_tools",
        "automation_tools",
        "audition_tools",
        "marker_tools",
        "folder_tools",
        "workspace_tools",
        "utility_tools",
    },
    # `banks` — bank management, platform/build surface + minimal project.
    "banks": {
        "project_tools",
        "bank_tools",
        "folder_tools",
        "workspace_tools",
        "utility_tools",
    },
    # `minimal` — smoke test / verify the bridge + read the project tree.
    "minimal": {
        "project_tools",
        "utility_tools",
        "workspace_tools",
    },
}

# Every module name that should exist on disk in a healthy checkout — update
# this when adding a new fmod_mcp/tools/*.py module. This is what lets the
# `full` profile fail loud if a module goes missing (e.g. an overly-broad
# .gitignore rule silently dropping shipped files) instead of the server
# quietly booting with fewer tools than intended.
_EXPECTED_MODULES = frozenset(
    {
        "audition_tools",
        "automation_tools",
        "bank_tools",
        "event_tools",
        "folder_tools",
        "marker_tools",
        "mixer_tools",
        "parameter_tools",
        "project_tools",
        "snapshot_tools",
        "sound_tools",
        "utility_tools",
        "workspace_tools",
    }
)


def _resolve_profile() -> tuple[str, set[str] | None]:
    """Read FMOD_STUDIO_MCP_PROFILE from env, validate, return (name, module_set)."""
    raw = os.environ.get("FMOD_STUDIO_MCP_PROFILE", "full").strip().lower()
    if raw not in PROFILES:
        sys.stderr.write(
            f"[fmod-studio-mcp] \u26a0\ufe0f  Unknown FMOD_STUDIO_MCP_PROFILE='{raw}'. "
            f"Valid: {', '.join(sorted(PROFILES))}. Falling back to 'full'.\n"
        )
        raw = "full"
    return raw, PROFILES[raw]


def register_all_tools(mcp: FastMCP):
    """Discover and register every tool module in fmod_mcp/tools/.

    A module counts as a tool provider if it exports `register(mcp)`. Modules
    without that function are skipped silently (they may be helpers).

    Respects the FMOD_STUDIO_MCP_PROFILE environment variable. Valid values:
    `full` (default), `events`, `mixer`, `banks`, `minimal`. A profile
    filters which modules are registered, trimming the tool surface so it
    fits under LLM tool-count limits (Groq Llama 3 = 128, etc.).

    If a module raises during import or registration, we log loudly and ALSO
    write a banner to stderr so the failure is obvious even when log output
    is hidden by the harness. We keep loading the rest so one broken file
    doesn't take the server down.
    """
    profile_name, allowed = _resolve_profile()

    failures: list[tuple[str, Exception]] = []
    registered: list[str] = []
    skipped_by_profile: list[str] = []

    for _finder, name, _ispkg in pkgutil.iter_modules(tools_package.__path__):
        if allowed is not None and name not in allowed:
            skipped_by_profile.append(name)
            continue

        try:
            module = importlib.import_module(f"fmod_mcp.tools.{name}")
        except Exception as e:
            logger.error("IMPORT FAILED for tool module %s: %s", name, e, exc_info=True)
            sys.stderr.write(
                f"\n[fmod-studio-mcp] \u274c Failed to import tool module '{name}': {e}\n"
            )
            failures.append((name, e))
            continue

        if not hasattr(module, "register"):
            logger.debug("Module %s has no register() — skipping", name)
            continue

        try:
            module.register(mcp)
            logger.info("Registered tools from %s", name)
            registered.append(name)
        except Exception as e:
            logger.error("REGISTER FAILED for %s: %s", name, e, exc_info=True)
            sys.stderr.write(
                f"\n[fmod-studio-mcp] \u274c Tool registration failed for '{name}': {e}\n"
            )
            failures.append((name, e))

    banner = f"[fmod-studio-mcp] Profile '{profile_name}' — registered {len(registered)} tool module(s)"
    if allowed is not None and skipped_by_profile:
        banner += f", skipped {len(skipped_by_profile)} (not in profile)"
    sys.stderr.write(banner + "\n")

    # Sanity check — compare what's actually on disk/registered against the
    # known-good module set. Runs for every profile, including the default
    # `full` (allowed=None), which otherwise has nothing to compare against.
    expected = (
        (allowed & _EXPECTED_MODULES) if allowed is not None else _EXPECTED_MODULES
    )
    missing = sorted(expected - set(registered) - {n for n, _ in failures})
    truly_missing = []
    for name in missing:
        try:
            importlib.import_module(f"fmod_mcp.tools.{name}")
        except ModuleNotFoundError:
            truly_missing.append(name)
        except Exception:  # noqa: S110
            pass  # some other problem — already surfaced via failures
    if truly_missing:
        sys.stderr.write(
            f"[fmod-studio-mcp] \u26a0\ufe0f  Profile '{profile_name}' is missing expected "
            f"module(s) that don't exist on disk: {truly_missing}. This "
            f"install is incomplete — those tools will not be available.\n"
        )

    if failures:
        sys.stderr.write(
            f"\n[fmod-studio-mcp] \u26a0\ufe0f  {len(failures)} tool module(s) failed to load: "
            f"{', '.join(n for n, _ in failures)}\n"
            f"[fmod-studio-mcp] The server is running but those tools are unavailable.\n\n"
        )
