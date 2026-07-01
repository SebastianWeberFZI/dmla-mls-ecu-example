@echo off
set SCRIPT=%~dp0check_ecu_mls.py

where python >nul 2>nul
if %ERRORLEVEL%==0 (
    python "%SCRIPT%"
    exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 "%SCRIPT%"
    exit /b %ERRORLEVEL%
)

set BUNDLED_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
if exist "%BUNDLED_PYTHON%" (
    "%BUNDLED_PYTHON%" "%SCRIPT%"
    exit /b %ERRORLEVEL%
)

echo Python 3 was not found. Install Python or run check_ecu_mls.py with a Python 3 interpreter.
exit /b 1
