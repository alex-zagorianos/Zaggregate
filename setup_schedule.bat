@echo off
rem Register the daily headless job search in Windows Task Scheduler (07:30).
rem Run once (double-click). Remove with: schtasks /Delete /TN JobSearchDaily /F
set SCRIPT_DIR=%~dp0
schtasks /Create /F /SC DAILY /ST 07:30 /TN "JobSearchDaily" ^
  /TR "cmd /c cd /d \"%SCRIPT_DIR:~0,-1%\" && py daily_run.py"
if %ERRORLEVEL%==0 (
    echo.
    echo Scheduled: JobSearchDaily runs every day at 07:30.
    echo Log: %SCRIPT_DIR%output\daily_run.log
) else (
    echo.
    echo FAILED to create the task. Try running this .bat as Administrator.
)
pause
