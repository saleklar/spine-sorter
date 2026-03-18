
@echo off
echo ========================================================
echo PUBLISHING NEW VERSION TO GITHUB
echo ========================================================
echo This will commit all changes, create a version tag, and push.
echo GitHub Actions will then automatically build Windows EXE + Mac .app
echo and attach them to a new GitHub Release.
echo.
echo Make sure APP_VERSION in spine sorter 257.py is updated first!
echo.

:: Read version from the Python file
for /f "tokens=3 delims= " %%a in ('findstr "APP_VERSION = " "spine sorter 257.py"') do set RAW_VERSION=%%a
:: Strip surrounding quotes
set VERSION=%RAW_VERSION:"=%
set TAG=v%VERSION%

echo Detected version: %VERSION%  (will tag as %TAG%)
echo.
pause

echo Updating version.txt gatekeeper to %VERSION%...
echo %VERSION%> version.txt

echo Committing...
git add "spine sorter 257.py" "CHANGELOG.md" ".github/workflows/build.yml" "build_mac.sh" "version.txt"
git commit -m "RELEASE: %TAG%"

echo Creating tag %TAG%...
git tag %TAG%

echo Pushing commits and tag...
git push
git push origin %TAG%

echo.
echo DONE. GitHub Actions will now build Windows + Mac and attach to Release %TAG%.
echo Check progress at: https://github.com/[your-repo]/actions
pause
