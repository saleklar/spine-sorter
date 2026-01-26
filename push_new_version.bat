@echo off
echo Bumping version...
python tools/bump_version.py

echo Committing version bump...
git add "spine sorter 257.py" "Spine Sorter 257.spec" "build_mac.sh"
git commit -m "Auto-bump version"

echo Pushing...
git push
