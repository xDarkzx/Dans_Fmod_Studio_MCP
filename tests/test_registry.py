import importlib

from fmod_mcp import tool_registry
from fmod_mcp.tools import _common


class _StubMCP:
    """Minimal stand-in for FastMCP exposing just the tool() decorator."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _iter_tool_modules():
    import fmod_mcp.tools as pkg
    import pkgutil

    # Skip underscore-prefixed helpers (`_common` is intentionally not a
    # provider) — only real tool modules must expose register().
    return [
        m.name for m in pkgutil.iter_modules(pkg.__path__) if not m.name.startswith("_")
    ]


def test_expected_modules_exist_on_disk():
    for name in tool_registry._EXPECTED_MODULES:
        importlib.import_module(f"fmod_mcp.tools.{name}")


def test_every_module_registers():
    for name in _iter_tool_modules():
        mod = importlib.import_module(f"fmod_mcp.tools.{name}")
        assert callable(getattr(mod, "register", None)), f"{name} lacks register()"


def test_helper_module_explicitly_not_a_provider():
    assert not hasattr(_common, "register")


def test_profiles_reference_only_real_modules(monkeypatch):
    known = set(_iter_tool_modules())
    for profile, modules in tool_registry.PROFILES.items():
        if modules is None:
            continue
        unknown = set(modules) - known
        assert not unknown, f"profile {profile} references unknown modules: {unknown}"


def test_unknown_profile_falls_back_to_full(monkeypatch):
    monkeypatch.setenv("FMOD_STUDIO_MCP_PROFILE", "not-a-profile")
    name, allowed = tool_registry._resolve_profile()
    assert name == "full"
    assert allowed is None


def test_profile_resolution(monkeypatch):
    monkeypatch.setenv("FMOD_STUDIO_MCP_PROFILE", "mixer")
    name, allowed = tool_registry._resolve_profile()
    assert name == "mixer"
    assert "mixer_tools" in allowed
    assert "event_tools" not in allowed


def test_register_all_tools_respects_profile(monkeypatch):
    monkeypatch.setenv("FMOD_STUDIO_MCP_PROFILE", "events")
    mcp = _StubMCP()
    tool_registry.register_all_tools(mcp)
    # `events` profile = project + event + sound + parameter + folder + utility
    assert "event_create" in mcp.tools
    assert "mixer_group_create" not in mcp.tools
    assert "bank_create" not in mcp.tools
