@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python collector\collect.py --days 3 --budget 300
python tools\publish_private.py
pause
