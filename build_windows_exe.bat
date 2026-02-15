@echo off
setlocal

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

pyinstaller --noconfirm --onefile --windowed --name RogueMacro app.py

echo.
echo Build complete: dist\RogueMacro.exe
pause
