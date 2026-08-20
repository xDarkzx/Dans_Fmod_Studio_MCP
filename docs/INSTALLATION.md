# Installation Guide

## Prerequisites

- **FMOD Studio 2.02 or newer** (the scripting terminal exists in current versions).
- Python 3.10+.
- An MCP client (Claude Desktop, Claude Code, Cursor, …).

## 1. Enable FMOD Studio's Script Server (one time)

The scripting terminal is **disabled by default**. Opening the console with **Ctrl+0 is not enough** — that only shows script output.

1. Launch **FMOD Studio** and open your project (`File → Open Project…` — the server won't bind on the welcome screen).
2. Open Preferences — `Edit → Preferences…` on Windows/Linux, or `FMOD Studio → Preferences…` on macOS.
3. On the **Interface** tab, in the **Script Server** section:
   - ✅ tick **Enable Script Server (requires restart)**
   - **Port:** `3663` (must match `FMOD_STUDIO_PORT` if you override it)
4. **Quit and relaunch FMOD Studio**, then reopen the project.

### Verify it's listening

```
# Windows
Test-NetConnection 127.0.0.1 -Port 3663

# macOS / Linux
nc -z 127.0.0.1 3663 && echo "listening"
lsof -nP -iTCP:3663 -sTCP:LISTEN
```

Every launch records the state to the newest log file:

- Windows: `%LOCALAPPDATA%\FMOD Studio\Logs\`
- macOS: `~/Library/Application Support/FMOD Studio/Logs/`
- Linux: `~/.config/FMOD Studio/Logs/`

```
[Scripting] ScriptServer started on 127.0.0.1 (3663)   <- enabled, good
[Scripting] ScriptServer is disabled.                  <- not enabled
```

## 2. Install FmodStudioMCP

**From PyPI** (once published):

```bash
pip install xdarkzx-fmod-studio-mcp
```

**From source:**

```bash
git clone https://github.com/xDarkzx/FmodStudioMCP.git
cd FmodStudioMCP
# then either:
pip install -e .            # bare install
# or use the one-click installer:
install.bat                 # Windows
./install.sh                # macOS / Linux
```

The `fmod-studio-mcp` console command is installed either way.

## 3. Configure your MCP client

**Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "fmod-studio": {
      "command": "fmod-studio-mcp"
    }
  }
}
```

**Claude Code / Cursor / others** — follow their MCP config docs; the server entry is identical.

Restart the client after editing the config.

### Environment overrides

- `FMOD_STUDIO_HOST` — default `127.0.0.1`.
- `FMOD_STUDIO_PORT` — default `3663`.
- `FMOD_STUDIO_MCP_PROFILE` — tool-surface profile: `full` (default), `events`, `mixer`, `banks`, `minimal`.
- `FMOD_STUDIO_MCP_NO_SUPERSEDE=1` — disable the "newer server takes over" self-retirement (see `fmod_mcp/main.py`); only needed for unusual clients that open two connections under one parent process.

## 4. First conversation

```
"List every event in the project"
```

If everything is wired up, you should get a capped list of the project's events. From there, try the authoring workflow in `00_core.md` / the main README.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| "Cannot reach FMOD Studio's scripting terminal…" | Script Server disabled. Re-enable + restart (the checkbox literally says "requires restart"). |
| Reaches but tools fail with `COMMAND_FAILED`/`lookup failed` | Studio parsed the script but the object doesn't exist — pass a `event:/…`-style path or a `{guid}` from an earlier result. |
| "Script Server is disabled" in the log despite ticking it | The checkbox says *requires restart* — a toggle without relaunching won't bind the port. |
| Nothing on 3663 though enabled | No project open (server binds only with an open project), or another app holds the port. |
| Tools time out after ~30 s | You hit a genuinely long operation that isn't routed through `execute_long`. Report it; bank build / audio import already use the 600 s budget. |
| Port mismatch | Preferences port and `FMOD_STUDIO_PORT` must match. |