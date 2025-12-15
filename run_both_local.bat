@echo off
REM Convenience script to run both Program A and Program B on localhost.
REM This opens two new command windows: one for A and one for B.

setlocal
cd /d "%~dp0"

start "Program B" cmd /k "python program_b.py --a-host 127.0.0.1 --udp-port 5000 --tcp-port 5001 --verbose"
start "Program A" cmd /k "python program_a.py --b-host 127.0.0.1 --udp-port 5000 --tcp-port 5001 --verbose"

endlocal
