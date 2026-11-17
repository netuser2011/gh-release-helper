@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GitHub Release Download Helper

rem ---------------------------------------------------------------------
rem  Launcher for the interactive GitHub Release downloader.
rem
rem  Keep this file ASCII-only, on purpose. cmd.exe re-reads a batch file
rem  by byte offset after chcp switches the code page, so any multi-byte
rem  (Chinese) text in a line can split the line in the middle and the
rem  tail gets executed as a command. Verified on this machine: an echo line
rem  holding CJK text ran a fragment of itself as a command, and another CJK
rem  echo left ERRORLEVEL at 1, which then fired the "install failed" branch
rem  even though nothing failed. Chinese messages therefore live in the
rem  Python program, not here.
rem ---------------------------------------------------------------------

rem --- locate a Python interpreter: check errorlevel at runtime, never %errorlevel% ---
set "PYCMD="
where py >nul 2>nul
if errorlevel 1 goto find_python
py -3 --version >nul 2>nul
if errorlevel 1 goto find_python
set "PYCMD=py -3"
goto python_found

:find_python
where python >nul 2>nul
if errorlevel 1 goto python_found
set "PYCMD=python"

:python_found

if not defined PYCMD (
    echo [ERROR] No Python interpreter found on PATH.
    echo         Install Python 3.10+ from https://www.python.org/downloads/
    echo         and tick "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)

rem --- install the only third-party dependency on first run ---
%PYCMD% -c "import requests" >nul 2>nul
if errorlevel 1 (
    echo First run: installing requests from requirements.txt ...
    %PYCMD% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Dependency install failed. Check your network or proxy,
        echo         then run this file again.
        echo.
        pause
        exit /b 1
    )
    echo Dependency ready.
    echo.
)

rem --- run ---
%PYCMD% main.py %*

echo.
echo Finished. Any traceback above is also saved in crash.log next to this file.
pause
