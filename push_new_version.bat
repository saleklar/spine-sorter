@echo off
echo ========================================================
echo PUBLISHING NEW VERSION TO GITHUB
echo ========================================================
echo This will bump the version, update version.txt, and lock out old clients.
echo.
echo If you just want to save work without releasing,
echo please use 'git add .', 'git commit', 'git push' instead.
echo.
pause

echo Bumping version...
python tools/bump_version.py

echo Committing version bump...
git add "spine sorter 257.py" "Spine Sorter 257.spec" "build_mac.sh" "version.txt"
git commit -m "RELEASE: Auto-bump version"

echo Pushing...
git push

rem We no longer need to copy to Z: drive since clients check GitHub directly
rem if exist "Z:\spine sorter v257" (
rem     echo Copying version.txt to Z:\spine sorter v257...
rem     copy /Y "version.txt" "Z:\spine sorter v257\version.txt"
rem )

echo.
echo DONE. Version is live on GitHub.
pause
