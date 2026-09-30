@echo off
setlocal
uv sync
if errorlevel 1 exit /b %errorlevel%
uv run pyinstaller --clean --onefile --name url-checker --collect-all DrissionPage --collect-all DrissionGet --collect-all DrissionRecord src\url_availability_checker\__init__.py
if errorlevel 1 exit /b %errorlevel%
echo Built dist\url-checker.exe
