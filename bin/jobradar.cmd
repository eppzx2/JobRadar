@echo off
setlocal
pushd "%~dp0.." || exit /b 1
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" app.py --server.headless=false %*
) else (
    where py.exe >nul 2>&1
    if errorlevel 1 (
        python app.py --server.headless=false %*
    ) else (
        py -3 app.py --server.headless=false %*
    )
)
set "jobradar_exit=%errorlevel%"
popd
exit /b %jobradar_exit%
