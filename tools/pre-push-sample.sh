# This is a sample pre-push hook to automatically bump version
# To use it, rename this file to 'pre-push' (no extension) and move it to .git/hooks/
# Note: Modifying files in pre-push is complex because you need to commit them and push the NEW commit.

#!/bin/sh

echo "Running pre-push hook: Bumping version..."

# run the python script
python tools/bump_version.py

# Check if any files were modified
if git diff --quiet; then
    echo "No version change needed."
else
    echo "Version bumped. Committing and updating push..."
    git add "spine sorter 257.py" "Spine Sorter 257.spec" "build_mac.sh"
    git commit -m "Auto-bump version"
    
    # We are in the middle of a push command. Pushing a new commit now might be recursive or confusing.
    # Standard practice is to FAIL this push and ask user to push again with new commit, 
    # OR (advanced) update the ref being pushed. 
    
    # Simple approach: Fail and ask user to push again.
    echo "Version bumped and committed. Please run 'git push' again to push the new version."
    exit 1
fi

exit 0
