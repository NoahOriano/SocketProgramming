@echo off
REM Simple helper script to run Program B (UDP server + TCP client)
REM from the SocketProgramming directory.

setlocal
cd /d "%~dp0"

python program_b.py --a-host 127.0.0.1 --udp-port 5000 --tcp-port 5001 --verbose

endlocal
