@echo off
REM Start the local browser-receiver server.
REM
REM  - Browser receiver + web UI:  http://localhost:5002  (extension + /app)
REM
REM S36: the standalone job tracker on :5001 (tracker/app.py) was RETIRED — its
REM routes folded into the receiver on :5002, and the browser extension now talks
REM only to :5002. Resume generation lives in the desktop GUI / the web UI.
REM
REM For the modern web UI instead of the tkinter GUI, run:  py -m webui
REM (opens http://localhost:5002/app in your browser).

start "Browser Receiver"   cmd /k py -m scrape.browser_receiver

echo Server started.
echo   Browser receiver + web UI:  http://localhost:5002
echo   (web UI: run  py -m webui  to open http://localhost:5002/app)
pause
