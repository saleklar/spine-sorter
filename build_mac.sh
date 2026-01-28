#!/bin/bash
# Script to build Spine Sorter on macOS

# Ensure we are in the script's directory
cd "$(dirname "$0")"

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Clean previous builds
rm -rf build dist

# Build the application
echo "Building application..."
pyinstaller --noconfirm --onefile --windowed --name "Spine Sorter v5.52" "spine sorter 257.py"

echo "Build complete. Check the 'dist' folder for 'Spine Sorter v5.52.app'."
