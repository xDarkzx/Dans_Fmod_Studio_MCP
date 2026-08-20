import json

import pytest

from fmod_mcp_shared.error_codes import ErrorCode, FmodMCPError
from fmod_mcp_shared.protocol import format_command, parse_response

_PREFIX = "(function(){const p="


def _extract_params(js: str) -> dict:
    """Pull the `const p=...` object literal back out of a wrapper and parse it."""
    assert js.startswith(_PREFIX), f"wrapper prefix missing: {js[:60]!r}"
    assert js.endswith("})()"), f"wrapper suffix missing: {js[-40:]!r}"

    # Find the closing of the params object: the next `};` after the prefix.
    rest = js[len(_PREFIX) :]
    depth = 0
    for i, ch in enumerate(rest):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                literal = rest[: i + 1]
                return json.loads(literal)
            if depth < 0:
                break
    raise AssertionError("could not locate params object")


def _balance(js: str) -> None:
    """Crude JS structural check — braces/parens/brackets must balance."""
    pairs = {"}": "{", ")": "(", "]": "["}
    stack = []
    in_str = False
    esc = False
    for ch in js:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{([":
            stack.append(ch)
        elif ch in "})]":
            assert stack and stack[-1] == pairs[ch], (
                f"mismatched '{ch}' near ...{js[max(0, js.index(ch) - 40) : js.index(ch) + 40]}..."
            )
            stack.pop()
    assert not stack, f"unbalanced: {stack}"


class TestFormatCommand:
    def test_wraps_body_with_params(self):
        js = format_command("return p.x;", x=42)
        assert _extract_params(js) == {"x": 42}
        assert "return p.x;" in js
        _balance(js)

    def test_nested_json_params_survive(self):
        js = format_command("return p.data;", data={"a": [1, 2], "b": "x"})
        assert _extract_params(js) == {"data": {"a": [1, 2], "b": "x"}}
        _balance(js)

    def test_body_with_braces_is_not_misread_as_format_fields(self):
        # The whole point of concatenation over str.format: JSON and JS both
        # use { }, and str.format would try to expand them as fields.
        js = format_command("return {a:1,b:{c:2}};", x="y")
        assert "{a:1,b:{c:2}}" in js

    def test_quotes_and_unicode_in_params_stay_inert(self):
        evil = '";globalThis.x=1;//'
        js = format_command("return p.s;", s=evil)
        assert _extract_params(js)["s"] == evil
        _balance(js)

    @pytest.mark.parametrize("bad", ["\x00inside", "line\u2028sep", "para\u2029sep"])
    def test_injection_chars_rejected(self, bad):
        for kwargs in ({"s": bad}, {"s": "ok", "k": bad}):
            with pytest.raises(FmodMCPError) as ei:
                format_command("return p.s;", **kwargs)
            assert ei.value.code == ErrorCode.INJECTION_DETECTED

    @pytest.mark.parametrize("inner", ['";', '\\"', "));\\n", "</script>"])
    def test_common_js_breakouts_contained(self, inner):
        js = format_command("return p.s;", s=inner)
        params = _extract_params(js)
        assert params["s"] == inner
        _balance(js)

    def test_empty_command_ok(self):
        _balance(format_command("", x=1))


class TestParseResponse:
    def test_clean(self):
        assert parse_response('{"success":true,"result":5}') == {
            "success": True,
            "result": 5,
        }

    def test_clean_with_noise_around_it(self):
        # console.log output precedes the evaluated result on the terminal.
        assert parse_response(
            'log noise\n{"success":true,"result":{"guid":"{abc}"}}\n'
        ) == {
            "success": True,
            "result": {"guid": "{abc}"},
        }

    def test_empty(self):
        r = parse_response("")
        assert r["success"] is False
        assert "Empty" in r["error"]

    def test_undefined_result(self):
        r = parse_response("undefined")
        assert r["success"] is False

    def test_garbage(self):
        r = parse_response("not json at all")
        assert r["success"] is False
        assert "raw" in r

    def test_error_result_forwarded(self):
        r = parse_response('{"success":false,"error":"boom"}')
        assert r == {"success": False, "error": "boom"}

    def test_multiple_json_objects_picks_first_with_success(self):
        r = parse_response('{"a":1}\n{"success":true,"result":"yes"}')
        assert r["success"] is True


@pytest.mark.parametrize(
    "body,params",
    [
        ("return p.x;", {"x": "a/b"}),
        ("return p.x;", {"x": 3.5}),
        ("return p.x;", {"x": ["u", "v"]}),
        ("return p.x;", {}),
    ],
)
def test_full_wrapper_roundtrips_params(body, params):
    js = format_command(body, **params)
    assert _extract_params(js) == params
    _balance(js)
