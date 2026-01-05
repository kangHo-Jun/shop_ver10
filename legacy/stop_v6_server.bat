@echo off
echo Stopping V6 Server...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq V6*" 2>nul
taskkill /F /IM python.exe /FI "MEMUSAGE gt 50000" 2>nul
echo Server stopped.
timeout /t 2
