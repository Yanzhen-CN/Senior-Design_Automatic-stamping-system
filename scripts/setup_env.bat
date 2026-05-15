@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

pushd "%PROJECT_ROOT%" || exit /b 1

conda env list | findstr /R /C:"^SD " /C:"^SD$" >nul
if errorlevel 1 (
  echo Creating conda environment SD...
  conda env create -f environment.yml
) else (
  echo Updating conda environment SD...
  conda env update -n SD -f environment.yml --prune
)

if errorlevel 1 (
  echo Environment setup failed.
  popd
  exit /b %errorlevel%
)

echo Environment SD is ready.
popd
endlocal

