"""Shared JS-building helpers for tool modules (no tools registered here).

Kept out of the tools' individual files so every *list-style* command emits
the same capped, mapped result shape:
    [{guid, name, path}, ...]
instead of leaking raw ManagedObjects into JSON.stringify.
"""

from fmod_mcp_shared.constants import MAX_OBJECTS_READ, MAX_SOUNDS_READ


def js_list(expr: str, cap: int = MAX_OBJECTS_READ) -> str:
    """Build a command body that maps an object-array expression to info dicts.

    `expr` must evaluate to an array of ManagedObjects (or undefined). Safe
    against a null from a broken call: the `|| []` guards it into an empty
    list, and the cap keeps a giant project from flooding the model's context.
    """
    cap = int(cap)
    return (
        f"var __a=({expr})||[];var __o=[];"
        f"for(var __i=0;__i<__a.length&&__i<{cap};__i++){{"
        f"__o.push({{guid:G(__a[__i]),name:N(__a[__i]),path:P(__a[__i])}});}}"
        f"return __o;"
    )


def js_info(expr: str) -> str:
    """Build a command body that returns the canonical info dict for one object."""
    return f"var __o=({expr});return {{guid:G(__o),name:N(__o),path:P(__o)}};"


# Max instruments reported per track/event listing — stricter than the generic
# object cap because a busy event can carry many sounds, and instrument
# payloads are heavier than bare object rows.
MAX_TRACK_LIST_SOUNDS = MAX_SOUNDS_READ
