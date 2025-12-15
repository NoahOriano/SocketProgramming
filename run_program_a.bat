@echo off
REM Simple helper script to run Program A (TCP server + UDP client)
REM from the SocketProgramming directory.

setlocal
cd /d "%~dp0"

python program_a.py --b-host 127.0.0.1 --udp-port 5000 --tcp-port 5001 --verbose

endlocal
