@echo off
cd /d "%~dp0docs"
echo.
echo === iPhone (same Wi-Fi) : open this address in Safari ===
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo   http://%%a:8000/
echo (If Windows asks about the firewall, allow PRIVATE networks only.)
echo (Close this window to stop.)
echo.
python -m http.server 8000 --bind 0.0.0.0
