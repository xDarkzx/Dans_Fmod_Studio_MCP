# Contributing

FmodStudioMCP follows the same conventions as its sibling [Reaper-MCP](https://github.com/xDarkzx/Reaper-MCP). If you've contributed there, everything below already applies.

## Ground rules

- **No arbitrary-script tools.** Every tool is a named, schema-validated operation. The FMOD JS terminal is powerful — an `eval`-style escape hatch would let a model wreck a sound designer's project with no guardrails.
- **Validate before sending.** Ranges (dB, counts, durations), name lengths, type/enum whitelists, and file paths/extensions are checked Python-side so Studio never sees garbage.
- **Params travel as JSON, never interpolated into JS.** See `fmod_mcp_shared/protocol.py`. A string must not be able to break out of its quotes — that's a security invariant, covered by tests.
- **Conservative read caps.** Context windows fill fast. List there is capped, read N. A huge project must never flood the reply.
- **One module = one concern.** Events vs sounds vs mixer vs banks stay separate files. The registry discovers modules automatically — keep that contract.

## Adding a new tool

1. Add to the right module in `fmod_mcp/tools/` (or create a new one) and export a `register(mcp: FastMCP)` function.
2. Define your tool with `@mcp.tool()`. The function signature is the schema — docstrings become the tool descriptions, and every parameter needs `Args:` lines.
3. Return `await client.execute("js command body", **params)` (or `execute_long` for bank builds / audio imports). The body is the *inside* of a function; use the injected helpers `G`, `N`, `P`, `L` and the `p` param object.
4. Add the module to `_EXPECTED_MODULES` in `tool_registry.py`, and to any profile in `PROFILES` that should include it.
5. Add tests that exercise the new tool — the harness in `tests/test_tools_registration.py` will call it with sample args automatically once it's registered, but add specific assertions for validation rules you introduced.

## Naming

- Tool functions: `domain_action` (e.g. `sound_set_audio_file`, `bank_add_event`).
- Domain prefixes: `project_*`, `event_*`, `audio_*`, `sound_*`, `parameter_*`, `bank_*`, `mixer_*`, `folder_*`, `workspace_*`, `utility_*`.

## JS command conventions

Keep command bodies small and defensive:

- Resolve references with `L(p.target)` (throws a typed message if lookup fails).
- Serialize results into plain objects: `{guid: G(o), name: N(o), path: P(o)}`.
- Guard optional API features with feature checks (`try/catch` or `typeof`), so a script never hard-fails because a newer/older Studio lacks a member.
- List results via the shared mapper in `fmod_mcp/tools/_common.py`.

## Quality gates

```bash
pip install -e ".[dev]"
pytest tests/ -x -q     # must stay green
ruff check .            # F (bugs) + S (security) only — no style linting
```

## Release checklist

- Bump `version` in `pyproject.toml`.
- Add a `CHANGELOG.md` entry.
- Tag the release on GitHub (`git tag vX.Y.Z && git push --tags`).