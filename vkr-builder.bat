@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY_CMD="
set "PY_ARGS="
rem Name the tool answers to in usage lines, hints and help.
set "VKR_PROG=vkr-builder.bat"

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY_CMD=py"
    set "PY_ARGS=-3"
    goto :run
  )
)

where python3 >nul 2>&1
if %ERRORLEVEL%==0 (
  python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY_CMD=python3"
    goto :run
  )
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY_CMD=python"
    goto :run
  )
)

echo.
echo   x Python 3.10 or newer was not found
echo     install Python, or add it to PATH, then run this again
echo.
echo     try  https://www.python.org/downloads/
echo.
exit /b 1

:run
if defined PY_ARGS (
  "%PY_CMD%" %PY_ARGS% "%~dp0main.py" %*
) else (
  "%PY_CMD%" "%~dp0main.py" %*
)
exit /b %ERRORLEVEL%
