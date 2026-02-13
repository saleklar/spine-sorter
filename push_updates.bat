@echo off
echo Adding changes...
git add "spine sorter 257.py"

echo Committing...
git commit -m "Fix folder naming and improve version detection with brute-force fallback"

echo Pushing to GitHub...
git push

echo Done!
pause