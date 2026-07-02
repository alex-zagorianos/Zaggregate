@echo off
rem LEGACY (superseded by the projects system; kept for reference). Run from repo root.
cd /d "%~dp0\.."
py -m search.cli --user-config legacy/config_dad.json
pause
