@echo off
rem Register the daily headless job search in Windows Task Scheduler.
rem
rem This now delegates to scripts\setup_schedule.py, which registers ONE task per
rem project (JobSearchDaily_<slug>), staggered a few minutes apart, honoring each
rem project's `daily` flag in projects.json. Pre-migration (no projects/) it tells
rem you to use a single-project task instead.
rem
rem Run once (double-click). Remove a task with:
rem   schtasks /Delete /TN JobSearchDaily_<slug> /F
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR:~0,-1%"
py scripts\setup_schedule.py
if %ERRORLEVEL%==0 (
    echo.
    echo Per-project daily tasks registered.
) else (
    echo.
    echo FAILED to register tasks. Try running this .bat as Administrator.
)
pause
