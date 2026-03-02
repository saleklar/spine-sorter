@echo off
echo Building Spine Sorter EXE...
echo.

:: Activate Virtual Environment if present
if exist ".venv\Scripts\activate.bat" (
    echo Activating venv...
    call ".venv\Scripts\activate.bat"
)

:: Clean previous build
if exist "dist\*.exe" (
    echo Deleting old builds...
    del "dist\*.exe"
)

:: Run PyInstaller using the full path to python/script
echo Running PyInstaller...
python -m PyInstaller --clean "Spine Sorter 257.spec" --noconfirm

echo.
:: Check for any EXE in dist folder
if exist "dist\*.exe" (
    echo ========================================================
    echo BUILD SUCCESSFUL!
    echo ========================================================
    echo File(s) located at:
    dir /b "dist\*.exe"
    echo.
    echo Opening folder...
    start "" "dist"
    echo.
    echo NOW: Go to GitHub Releases and upload this file.
) else (
    echo ========================================================
    echo BUILD FAILED. Check errors above.
    echo ========================================================
)
pause