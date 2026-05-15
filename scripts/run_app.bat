@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

pushd "%PROJECT_ROOT%" || exit /b 1
echo Starting desktop app...
conda run -n SD python desktop\pywebview\app.py
popd
endlocal

