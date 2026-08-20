import os

_INSTRUCTIONS_DIR = os.path.dirname(os.path.abspath(__file__))


def load_instructions() -> str:
    """Load the concatenated instruction markdown files (00_core.md first).

    The files are installed as package data, so this works from an installed
    wheel as well as from a source checkout. FastMCP injects the result as
    the server's `instructions`, giving the model the FMOD-specific authoring
    guidance without any of it living in tool docstrings.
    """
    parts = []
    for fname in sorted(os.listdir(_INSTRUCTIONS_DIR)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(_INSTRUCTIONS_DIR, fname)
        with open(path, encoding="utf-8") as f:
            parts.append(f.read())
    return "\n\n".join(parts)
