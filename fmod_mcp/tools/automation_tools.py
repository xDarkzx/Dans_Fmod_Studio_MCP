from mcp.server.fastmcp import FastMCP

from fmod_mcp_shared.constants import MAX_AUTOMATION_POINTS
from fmod_mcp_shared.error_codes import FmodMCPError, ErrorCode

# Properties the scripting API exposes to addAutomator(). Confirmed against
# the official reference: mixer groups/buses/VCAs automate `volume`; events
# automate `volume`/`pitch`; mixer effects automate their control params
# (e.g. GainEffect automates `gain`).
ALLOWED_AUTOMATOR_PROPERTIES = ("volume", "pitch", "gain")

# curve.addAutomationPoint(position, value): `position` must fall within the
# driving parameter's range (parameter-driven) or the event timeline's range
# (timeline-driven); `value` must be in the automated property's range.
ALLOWED_DRIVER_TYPES = ("parameter", "timeline")

# Guard rails for a single curve; parameter-driven volumes are typically a
# handful of points (map position -> db), so this keeps a batch call small
# and a runaway model from pinning Studio's main thread.
MAX_POINTS = MAX_AUTOMATION_POINTS

# Automator.addAutomationCurve(parameter) unconditionally CREATES a new
# curve every time it's called — confirmed live (four separate calls each
# with one point produced four separate one-point curves, not one curve
# with four points). It does not dedupe by driver despite what an earlier
# version of this file's docstrings assumed. Every automation_* tool must
# therefore look for an existing curve bound to the same driver first (a
# curve's `relationships.parameter` destination, matched by guid) and only
# create a new one if none exists — otherwise every incremental call
# fragments the automation instead of building one curve.
_FIND_OR_CREATE_CURVE_JS = (
    "var __curve=null;"
    "var __crel=automator.relationships.automationCurves;"
    "var __existing=(__crel&&__crel.destinations)?__crel.destinations:[];"
    "for(var __i=0;__i<__existing.length;__i++){"
    "var __prel=__existing[__i].relationships&&__existing[__i].relationships.parameter;"
    "var __pdest=__prel?__prel.destinations:null;"
    "var __pobj=(__pdest&&__pdest[0])?__pdest[0]:null;"
    "if(__pobj&&G(__pobj)===G(drv)){__curve=__existing[__i];break;}}"
    "if(!__curve){__curve=automator.addAutomationCurve(drv);}"
)


def _check_property(prop: str) -> None:
    if prop not in ALLOWED_AUTOMATOR_PROPERTIES:
        raise FmodMCPError(
            ErrorCode.INVALID_TYPE,
            f"invalid automatable property {prop!r}; use one of "
            f"{', '.join(ALLOWED_AUTOMATOR_PROPERTIES)}",
        )


def _check_points(points) -> list[list[float]]:
    if not isinstance(points, list) or not points:
        raise FmodMCPError(
            ErrorCode.INVALID_PARAMETER, "points must be a non-empty list"
        )
    if len(points) > MAX_POINTS:
        raise FmodMCPError(
            ErrorCode.VALUE_OUT_OF_RANGE, f"too many points (max {MAX_POINTS})"
        )
    clean = []
    for pt in points:
        if not (isinstance(pt, (list, tuple)) and len(pt) == 2):
            raise FmodMCPError(
                ErrorCode.INVALID_PARAMETER,
                "each point must be [position, value]",
            )
        try:
            clean.append([float(pt[0]), float(pt[1])])
        except (TypeError, ValueError) as e:
            raise FmodMCPError(
                ErrorCode.INVALID_PARAMETER, f"point values must be numbers: {e}"
            )
    return clean


def register(mcp: FastMCP):
    from fmod_mcp.main import client

    @mcp.tool()
    async def automation_add_curve(
        target: str,
        property: str,
        driver: str,
        points: list,
        driver_type: str = "parameter",
    ) -> dict:
        """Bind a property to a curve so it changes as the driver changes —
        e.g. crossfade music layers by automating each layer's `volume`
        against an "Intensity" parameter. Reuses an existing curve for the
        same target/property/driver if one exists (adding these points to
        it) rather than creating a duplicate — call automation_list first
        if unsure whether one's already there.

        Args:
            target: Mixer group/bus/VCA/event mixer group {guid} — NOT a
                    track guid (use mixerGroupGuid, not trackGuid).
            property: 'volume' | 'pitch' | 'gain'.
            driver: 'parameter:/Name' (parameter-driven) or 'event:/...'
                    (timeline-driven).
            driver_type: 'parameter' | 'timeline'.
            points: [[position, value], ...]. Parameter-driven: position is
                    a parameter value. Timeline-driven: position is seconds.
        """
        _check_property(property)
        if driver_type not in ALLOWED_DRIVER_TYPES:
            raise FmodMCPError(
                ErrorCode.INVALID_TYPE,
                f"invalid driver_type {driver_type!r}; use parameter | timeline",
            )
        pts = _check_points(points)

        # Resolving the driver differs by type: a parameter lookup returns an
        # object whose `.parameter` is the GameParameter that curves bind to;
        # a timeline driver is the event's `.timeline`.
        if driver_type == "parameter":
            resolve = (
                "var d=studio.project.lookup(p.driver);"
                "if(!d)throw new Error('parameter lookup failed: '+p.driver);"
                "var drv=d.parameter?d.parameter:d;"
            )
        else:
            resolve = (
                "var d=L(p.driver);"
                "var drv=d.timeline;"
                "if(!drv)throw new Error('no timeline on driver: '+p.driver);"
            )

        # Each item already ends in ';' — join with "" (NOT ","). Joining
        # semicolon-terminated statements with a comma produces `a;,b;,c;`,
        # a bare comma at statement position, which is a JS syntax error —
        # confirmed live: every call with 2+ points failed with "Invalid
        # JSON response from FMOD Studio" (a parse-time error, caught by
        # neither our try/catch nor a clean thrown-error response) since
        # this tool was first written. A single-point call never hit it,
        # which is how this went undetected this long.
        call = "".join(
            f"__curve.addAutomationPoint({pt[0]:g},{pt[1]:g});" for pt in pts
        )
        body = (
            "var t=L(p.target);"
            "var automator=t.addAutomator?t.addAutomator(p.property):null;"
            "if(!automator)throw new Error('target has no addAutomator() for property: '+p.property);"
            + resolve
            + _FIND_OR_CREATE_CURVE_JS
            + "if(!__curve)throw new Error('addAutomationCurve failed');"
            + call
            + "return {guid:G(__curve),target:p.target,property:p.property,"
            "driver_type:p.driver_type,driver:p.driver,points:p.points.length};"
        )
        return await client.execute(
            body,
            target=target,
            property=property,
            driver=driver,
            driver_type=driver_type,
            points=pts,
        )

    @mcp.tool()
    async def automation_add(
        target: str,
        property: str,
        driver: str,
        driver_type: str = "parameter",
        position: float = 0.0,
        value: float = 0.0,
    ) -> dict:
        """Add one point to an existing curve (or start a new one). Same
        target/driver/property reuses the matching curve.

        Args:
            target: Mixer group/bus/VCA/event mixer group {guid}.
            property: 'volume' | 'pitch' | 'gain'.
            driver: 'parameter:/Name' or 'event:/...'.
            driver_type: 'parameter' | 'timeline'.
            position: Parameter value or timeline seconds.
            value: Mapped property value.
        """
        _check_property(property)
        if driver_type not in ALLOWED_DRIVER_TYPES:
            raise FmodMCPError(
                ErrorCode.INVALID_TYPE,
                f"invalid driver_type {driver_type!r}; use parameter | timeline",
            )
        if driver_type == "parameter":
            resolve = (
                "var d=studio.project.lookup(p.driver);"
                "if(!d)throw new Error('parameter lookup failed: '+p.driver);"
                "var drv=d.parameter?d.parameter:d;"
            )
        else:
            resolve = (
                "var d=L(p.driver);"
                "var drv=d.timeline;"
                "if(!drv)throw new Error('no timeline on driver: '+p.driver);"
            )
        body = (
            "var t=L(p.target);"
            "var automator=t.addAutomator?t.addAutomator(p.property):null;"
            "if(!automator)throw new Error('target has no addAutomator() for property: '+p.property);"
            + resolve
            + _FIND_OR_CREATE_CURVE_JS
            + "__curve.addAutomationPoint(p.position,p.value);"
            + "return {curveGuid:G(__curve),target:p.target,property:p.property,"
            "driver:p.driver,position:p.position,value:p.value};"
        )
        return await client.execute(
            body,
            target=target,
            property=property,
            driver=driver,
            driver_type=driver_type,
            position=position,
            value=value,
        )

    @mcp.tool()
    async def automation_list(target: str, property: str = "volume") -> dict:
        """List the real automation curves + points on a target's automator
        for a given property — every curve's guid, the driver parameter it's
        bound to, and its actual [position, value] points.

        Args:
            target: The automated object (mixer group, bus, VCA, event).
            property: 'volume' | 'pitch' | 'gain' (default 'volume').
        """
        _check_property(property)
        return await client.execute(
            "var t=L(p.target);"
            "var available=(typeof t.addAutomator==='function');"
            "if(!available)return {target:p.target,property:p.property,"
            "available:false,curves:[]};"
            "var automator=t.addAutomator(p.property);"
            "var crel=automator.relationships.automationCurves;"
            "var curves=(crel&&crel.destinations)?crel.destinations:[];"
            "var out=[];"
            "for(var i=0;i<curves.length;i++){"
            "var prel=curves[i].relationships&&curves[i].relationships.parameter;"
            "var pdest=prel?prel.destinations:null;"
            "var pobj=(pdest&&pdest[0])?pdest[0]:null;"
            "var ptrel=curves[i].relationships&&curves[i].relationships.automationPoints;"
            "var pts=(ptrel&&ptrel.destinations)?ptrel.destinations:[];"
            "var ptOut=[];"
            "for(var j=0;j<pts.length;j++){ptOut.push([pts[j].position,pts[j].value]);}"
            "ptOut.sort(function(a,b){return a[0]-b[0];});"
            "out.push({guid:G(curves[i]),driverGuid:pobj?G(pobj):null,points:ptOut});}"
            "return {target:p.target,property:p.property,available:true,curves:out};",
            target=target,
            property=property,
        )
