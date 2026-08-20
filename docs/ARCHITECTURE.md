# FmodStudioMCP — Architecture

How FmodStudioMCP connects an AI client to FMOD Studio, how commands are wrapped and parsed, and where the safety rails live.

## Overview

```
┌──────────────┐   stdio    ┌──────────────┐   TCP 3663     ┌──────────────┐
│  MCP Client  │◄──────────►│ FmodStudioMCP│◄──────────────►│ FMOD Studio  │
│(AI assistant)│  (JSON-RPC)│   FastMCP    │  (JS eval)     │ (JS terminal)│
└──────────────┘            └──────────────┘                └──────────────┘
```

Three processes, two transports:

1. The **MCP client** (Claude Desktop, Claude Code, Cursor, …) speaks [Model Context Protocol](https://modelcontextprotocol.io) over stdio.
2. The **Python server** is a [FastMCP](https://github.com/jlowin/fastmcp) app that translates tool calls into JavaScript command payloads.
3. **FMOD Studio** runs its built-in Script Server (a TCP terminal on `127.0.0.1:3663`) that evaluates whatever it receives as JavaScript and replies with the evaluated result as a UTF-8 string.

Every round-trip is a fresh socket connection under a cross-process file mutex — no state leaks between calls, and two AI clients can share one Studio without their evals interleaving.

## The command wrapper

Each tool body is wrapped into a self-evaluating, error-trapping JavaScript IIFE:

```js
(function(){const p=<params-json>;
  var G=function(o){return o&&o.id?String(o.id):null};
  var N=function(o){return o&&o.name?String(o.name):null};
  var P=function(o){var pp=null;try{pp=(o&&o.getPath)?o.getPath():null;}catch(__e){}
                    return pp?String(pp):(o&&o.name?String(o.name):null)};
  var L=function(t){if(!t)throw new Error('target is required');var o=studio.project.lookup(t);
                   if(!o)throw new Error('lookup failed for: '+t);return o;};
  try{var __r=(function(){ <tool body> })();
      return JSON.stringify({success:true,result:__r});}
  catch(__e){return JSON.stringify({success:false,error:String(__e&&__e.message||__e)});}
})()
```

- **`p` is the only channel between Python and JS.** Tool params are JSON-encoded with `ensure_ascii=True` and injected as a literal — escaped as `\uXXXX`, a hostile string can't break out of its quotes, reach the body, or inject code. Null bytes and U+2028/U+2029 (which terminate JS string literals in several engines) are rejected up front.
- **`G/N/P`** normalize object results (`ManagedObject.id` — not `.guid`, which doesn't exist — becomes its string form; `path` calls the real `getPath()` method — not a `.path` property, which also doesn't exist — falling back to `name` only if that fails), so every reply is small, plain, JSON-safe data.
- **`L()`** centralizes reference resolution. `.lookup()` returns the object or null; a miss raises a message we surface as a typed error instead of an opaque `ReferenceError`.
- **The whole thing is built by concatenation, never `str.format`** — JS and JSON both use `{`/`}`, which `str.format` would misread as template fields. This is the single most important implementation detail for getting valid payloads.

## Request lifecycle

1. A tool calls `client.execute("js body", **params)` or `client.execute_long(...)`.
2. `_send` wraps the body via `format_command`, takes the asyncio mutex, then the cross-process **file mutex** (`%TEMP%\fmod_studio_mcp\ipc.mutex`, real OS lock via `msvcrt`/`fcntl`).
3. A fresh socket connects to the Script Server; the payload (+ newline) is sent.
4. The response is read with **read-until-idle** framing: `recv` every spin; once the socket has been quiet for `IDLE` (0.3 s, or 5 s for long commands), the buffer is the complete reply. No prompt/EOF marker exists on the terminal, so this is the only reliable framing.
5. `parse_response` finds the JSON object amid any incidental console noise and returns the canonical `{success, result|error}` dict.
6. A typed `FmodMCPError` is raised on failure (connection refused/timeout/lost, malformed reply, Studio-reported error) — the client never sees a silent hang.
7. A small record of every completed command (pass or fail) is archived to `%TEMP%\fmod_studio_mcp\history\` with 30-day retention, because the terminal's reply is consumed immediately — without this there's no record of what was sent.

## Error taxonomy

`fmod_mcp_shared/error_codes.py` mirrors ReaperMCP: `1000s` connection, `2000s` command, `3000s` validation. The two that matter most for a good first-run experience:

- **CONNECTION_REFUSED (1001)** — the Script Server isn't reachable. The message tells the user exactly what to do: Preferences → Interface → enable Script Server → restart → open a project.
- **COMMAND_FAILED (2000)** — Studio evaluated the script and it threw/rejected. The JS error string is forwarded verbatim.

## Safety limits

From `fmod_mcp_shared/constants.py`:

- `MAX_OBJECTS_READ = 500`, `MAX_SOUNDS_READ = 1000` — *read* caps on list tools, protecting the calling model's context window.
- `MAX_NAME_LENGTH = 200`, `MAX_BATCH_CREATE = 100` — *write* caps keeping any single call small (large batch scripts block Studio's main thread).
- `ALLOWED_CREATE_TYPES`, `ALLOWED_EFFECTS`, `ALLOWED_PARAM_TYPES`, `ALLOWED_SOUND_TYPES`, `ALLOWED_AUDIO_EXTENSIONS` — whitelists validated Python-side so Studio never receives a bogus type/name.
- `Timeouts`: `COMMAND = 30 s`, `LONG_COMMAND = 600 s` (bank build, audio import), connect 10 s.
- `fmod_mcp_shared/path_safety.py`: `safe_path()` blocks path traversal (`..`) and reads from system directories, applied to `audio_import`.
- `fmod_mcp/safety.py`: `ensure_backup()` saves the project and copies its directory (skipping `Assets`/`Build`) to a timestamped sibling once per session, before any of the five destructive tools (`event_delete`, `bank_delete`, `mixer_group_delete`, `snapshot_delete`, `utility_delete`) runs. Best-effort — a failed backup logs a warning and lets the operation proceed rather than blocking it.

## Project structure

```
FmodStudioMCP/
├── fmod_mcp/
│   ├── main.py                # FastMCP entry, UTF-8 fix, parent watchdog
│   ├── fmod_client.py         # TCP bridge: send, read-until-idle, mutex, history
│   ├── tool_registry.py       # Auto-discovers tool modules; profiles
│   ├── safety.py              # Pre-destructive-op backup safety net
│   ├── instructions/
│   │   └── 00_core.md         # System-prompt instructions injected via FastMCP
│   └── tools/
│       ├── _common.py         # Shared JS list/info builders (no tools)
│       ├── project_tools.py   # save/saveAll/build/info
│       ├── event_tools.py     # create/delete/tracks/params-surface/maxVoices
│       ├── audition_tools.py  # play/stop/pause/keyoff/playback status
│       ├── marker_tools.py    # marker tracks: named markers, regions, transitions
│       ├── sound_tools.py     # audio import + instrument placement
│       ├── parameter_tools.py # game parameters, labels, initial values
│       ├── bank_tools.py      # banks + event membership
│       ├── mixer_tools.py     # groups, routing, effects, master bus, VCAs, sends
│       ├── folder_tools.py    # hierarchy creation + listing
│       ├── workspace_tools.py # browser/editor selection, navigation
│       └── utility_tools.py   # generic lookup/list/delete/validate/dump
├── fmod_mcp_shared/
│   ├── constants.py           # endpoints, timeouts, safety caps
│   ├── error_codes.py         # FmodMCPError + ErrorCode enum
│   ├── path_safety.py         # safe_path(): traversal/system-dir guard
│   └── protocol.py            # format_command / parse_response wrapper math
├── tests/                     # pytest suite (protocol, client, registry, harness)
├── install.bat / install.sh
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
└── pyproject.toml
```