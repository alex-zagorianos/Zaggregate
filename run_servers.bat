@echo off
REM Start all three local servers in separate windows.
REM  - Resume generator:   http://localhost:5000
REM  - Job tracker:        http://localhost:5001
REM  - Browser receiver:   http://localhost:5002  (for browser extension)

start "Resume Generator"   cmd /k py -m resume.app
start "Job Tracker"        cmd /k py -m tracker.app
start "Browser Receiver"   cmd /k py -m scrape.browser_receiver

echo All three servers started.
echo   Resume generator:  http://localhost:5000
echo   Job tracker:       http://localhost:5001
echo   Browser receiver:  http://localhost:5002
pause
