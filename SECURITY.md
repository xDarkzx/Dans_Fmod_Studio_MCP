# Security Policy

## Reporting a Vulnerability

**Please do not open a public GitHub issue for a security vulnerability.** That publishes the details before a fix exists.

Instead, use GitHub's private reporting: go to the [Security tab](https://github.com/xDarkzx/FmodStudioMCP/security) → **Report a vulnerability**. This opens a private conversation only you and the maintainer can see, and lets you attach details/reproduction steps without exposing them publicly.

## What to Expect

This is a solo-maintained project, so response times aren't guaranteed on a fixed SLA, but a genuine security report will be prioritized ahead of regular feature work. You'll get an acknowledgement, and a fix (or an explanation if it turns out not to be exploitable) once it's been looked into.

## Scope

FmodStudioMCP runs locally and talks to FMOD Studio over a TCP connection to its built-in Script Server on your own machine (`127.0.0.1:3663` by default) — there's no server, no cloud component, and no network exposure by design. Relevant reports include things like:

- A way for a malicious project file, imported audio file, or MCP tool call to trigger unintended file access, code execution, or data exfiltration
- Path traversal or injection through any tool parameter, including anything that breaks out of the JSON-encoded `p` parameter object and reaches the raw JavaScript sent to FMOD Studio's scripting terminal
- Anything that lets an MCP client do more than the documented tools allow

Reports about the underlying FMOD Studio application itself belong with [Firelight Technologies](https://www.fmod.com/), FMOD's developer, not here.

## Supported Versions

Only the latest published version is supported. Please update (`pip install --upgrade xdarkzx-fmod-studio-mcp`) before reporting, in case it's already fixed.
