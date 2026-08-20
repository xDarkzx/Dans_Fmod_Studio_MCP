import json
import re

from fmod_mcp_shared.error_codes import FmodMCPError, ErrorCode

_DANGEROUS_CHARS = re.compile(r"[\x00\u2028\u2029]")

# Shared JS helpers injected into every command wrapper. They keep command
# bodies short and consistent, and pin the exact serialization shape we rely
# on for parsing responses. Params live in a `const p` literal injected by
# the wrapper — a JSON-encoded param can never reach these names, because
# JSON string escaping neutralizes every quote/line-separator.
#
#   G(o)  -> String(o.id)            ({...} form, as Studio reports it —
#            ManagedObject.id, NOT .guid; there is no .guid property.
#            Confirmed live against a running FMOD Studio 2.03.14 instance.)
#   N(o)  -> o.name
#   P(o)  -> o.getPath() (fallback o.name) — a METHOD (Event.getPath(),
#            MixerStrip.getPath(), ...), not a .path property. Also
#            confirmed live; a bare `o.path` is always undefined.
#   L(t)  -> studio.project.lookup(t) with a null/throw-check; raises a
#            message we can surface as a typed error, instead of letting the
#            model guess at a ReferenceError deep in Studio.
_JS_HELPERS = (
    "var G=function(o){return o&&o.id?String(o.id):null};"
    "var N=function(o){return o&&o.name?String(o.name):null};"
    "var P=function(o){var pp=null;"
    "try{pp=(o&&o.getPath)?o.getPath():null;}catch(__e){}"
    "return pp?String(pp):(o&&o.name?String(o.name):null)};"
    "var L=function(t){if(!t)throw new Error('target is required');"
    "var o=studio.project.lookup(t);"
    "if(!o)throw new Error('lookup failed for: '+t);return o;};"
)

_JS_OPEN = "(function(){const p="
_JS_MID = ";" + _JS_HELPERS + "try{var __r=(function(){"
_JS_CLOSE = (
    "})();return JSON.stringify({success:true,result:__r});}"
    "catch(__e){return JSON.stringify({success:false,"
    "error:String(__e&&__e.message||__e)});}})()"
)


def _validate_string(value: str) -> str:
    """Reject characters that would break the JS string/object boundary.

    \u2028 / \u2029 are line separators that terminate string literals in
    several JS engines even inside quotes; a literal NUL byte is hostile in
    any protocol. json.dumps(ensure_ascii=True) already escapes everything
    else, so this is the last injection vector worth guarding.
    """
    if _DANGEROUS_CHARS.search(value):
        raise FmodMCPError(
            ErrorCode.INJECTION_DETECTED,
            f"Value contains illegal characters: {value!r}",
        )
    return value


def _jparams(params: dict) -> str:
    """Serialize params into a JS object literal safe to embed in the wrapper.

    ensure_ascii=True makes everything (including otherwise-dangerous
    characters) come out as inert \\uXXXX escapes, so a param can never
    escape its string or its object position.
    """
    return json.dumps(params, ensure_ascii=True, allow_nan=False)


def format_command(command: str, **params) -> str:
    """Wrap a JS command body into a self-evaluating, error-trapping payload.

    The FMOD Script Server evaluates anything it receives as JavaScript and
    replies with the evaluated result as a UTF-8 string. A command is the
    *body* of a function (any statements; the last `return` is the result),
    and params are injected as a `const p = {...}` literal. The wrapper
    always returns a JSON object string — either {'success': true, 'result':
    ...} or {'success': false, 'error': ...} — so a rejected script, a thrown
    JS exception, and a clean result all arrive in the same parseable shape.

    Built by concatenation, never str.format: JSON params legitimately contain
    `{`/`}` which str.format would misread as template placeholders.
    """
    _validate_string(command)
    for key, val in params.items():
        _validate_string(key)
        if isinstance(val, str):
            _validate_string(val)

    return _JS_OPEN + _jparams(params) + _JS_MID + command + _JS_CLOSE


_RESPONSE_RE = re.compile(r"\{.*\}", re.DOTALL)


def _iter_json_objects(text: str):
    """Yield each top-level {...} JSON object in text, in order.

    The Script Server prints incidental console output before the evaluated
    result, and that noise may itself contain JSON (e.g. an object dumped for
    debugging). Using a brace-depth scan with string/escape awareness locates
    *every* object — including nested result payloads — instead of one greedy
    regex grab, so the caller can pick the object that actually carries the
    success/error envelope.
    """
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch != "{":
            i += 1
            continue
        depth = 0
        start = i
        in_str = False
        esc = False
        while i < n:
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        yield text[start : i + 1]
                        i += 1
                        break
            i += 1
        else:
            break


def parse_response(raw: str) -> dict:
    """Parse the terminal's reply into the canonical command result dict.

    The Script Server *prints* incidental output from code it evaluates
    (console.log and friends) before the evaluated result, so we look for a
    JSON object specifically rather than assuming the whole buffer parses.
    Prefer the *first* object bearing the success/error envelope — anything
    printed earlier was incidental, but if Studio's own output contains an
    envelope-less object (e.g. a debug dump), it is skipped. A parse failure
    produces a typed result dict, never a raise, so the client can surface
    "malformed response" instead of hanging.
    """
    raw = raw.strip()
    if not raw:
        return {"success": False, "error": "Empty response from FMOD Studio"}

    last_err = None
    for candidate in _iter_json_objects(raw):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError) as e:
            last_err = e
            continue
        if isinstance(data, dict) and "success" in data:
            return data

    match = _RESPONSE_RE.search(raw)
    if match:
        raw = match.group(0)

    return {
        "success": False,
        "error": f"Invalid JSON response from FMOD Studio: {last_err}",
        "raw": raw[:2000],
    }
