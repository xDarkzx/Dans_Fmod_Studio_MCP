@echo off
rem FmodStudioMCP installer for Windows
rem Installs the package (local editable install) and optionally configures Claude Desktop.
setlocal

echo.
echo === FmodStudioMCP installer ===
echo.

rem --- Locate python --------------------------------------------------------
set "PY=%PYTHON%"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python not found. Install Python 3.10+ first, then re-run.
    exit /b 1
)

echo [1/3] Installing package (editable)...
"%PY%" -m pip install -e . --quiet
if errorlevel 1 (
    echo Install failed. See the message above.
    exit /b 1
)

echo [2/3] Verifying the fmod-studio-mcp command...
"%PY%" -c "import fmod_mcp.main" || (echo Import check failed. && exit /b 1)

echo [3/3] Next step: enable FMOD Studio's Script Server once.
echo        Preferences ^> Interface ^> tick "Enable Script Server" ^> restart Studio.
echo        Then add to your MCP client:
echo.
echo        "fmod-studio": { "command": "fmod-studio-mcp" }
echo.
echo Done.
endlocal