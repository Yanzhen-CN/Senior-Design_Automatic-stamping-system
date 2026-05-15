@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

pushd "%PROJECT_ROOT%" || exit /b 1
echo Starting web controller at http://127.0.0.1:8000
conda run -n SD python run_server.py
popd
endlocal

