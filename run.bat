@powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\launcher.ps1" %* & call exit /b %%errorlevel%%
