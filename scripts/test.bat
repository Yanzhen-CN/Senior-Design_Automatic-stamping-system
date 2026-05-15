@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

pushd "%PROJECT_ROOT%" || exit /b 1
conda run -n SD python -B -m unittest discover -s tests
popd
endlocal

