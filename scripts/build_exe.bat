@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

pushd "%PROJECT_ROOT%" || exit /b 1

echo Building AutomaticStampingSystem.exe...
conda run -n SD python -m PyInstaller desktop\pywebview\AutomaticStampingApp.spec --noconfirm --distpath desktop\pywebview\dist --workpath desktop\pywebview\build
if errorlevel 1 (
  echo Build failed. If PyInstaller is missing, run scripts\setup_env.bat first.
  popd
  exit /b %errorlevel%
)

if not exist "desktop\pywebview\dist\AutomaticStampingSystem.exe" (
  echo Build finished but the exe was not found.
  popd
  exit /b 1
)

echo Done: desktop\pywebview\dist\AutomaticStampingSystem.exe
popd
endlocal

