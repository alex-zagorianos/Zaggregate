@echo off
REM Start the local servers in separate windows.
REM  - Job tracker:        http://localhost:5001
REM  - Browser receiver:   http://localhost:5002  (for browser extension)
REM Resume generation lives in the desktop GUI now (the dead Flask resume
REM server was removed); run the GUI with: py -m gui

start "Job Tracker"        cmd /k py -m tracker.app
start "Browser Receiver"   cmd /k py -m scrape.browser_receiver

echo Servers started.
echo   Job tracker:       http://localhost:5001
echo   Browser receiver:  http://localhost:5002
pause
