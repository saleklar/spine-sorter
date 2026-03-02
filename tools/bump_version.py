import os
import re
import sys

# Define the regex to find the version string "Spine Sorter vX.XX" or APP_VERSION = "X.XX"
VERSION_REGEX = r'Spine Sorter v(\d+\.\d+)'
APP_VERSION_REGEX = r'APP_VERSION\s*=\s*"(\d+\.\d+)"'

# Files relative to this script (tools/bump_version.py)
FILES = [
    "../spine sorter 257.py",
    "../Spine Sorter 257.spec",
    "../build_mac.sh"
]

def bump():
    # Get the directory where this script sits (tools/)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.dirname(base_dir)
    
    # Read current version from the main python file
    main_file = os.path.join(base_dir, FILES[0])
    if not os.path.exists(main_file):
        print(f"Error: {main_file} not found.")
        return

    with open(main_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Try to find version in APP_VERSION first (more reliable for code)
    match = re.search(APP_VERSION_REGEX, content)
    if not match:
        # Fallback to header
        match = re.search(VERSION_REGEX, content)
        
    if not match:
        print("Could not find version string in main file.")
        return
        
    current_ver = match.group(1)
    
    # Increment logic (preserves two digits for minor if it started with 0 e.g. .04 -> .05)
    parts = current_ver.split('.')
    if len(parts) < 2:
        print(f"Unknown version format: {current_ver}")
        return

    major = parts[0]
    minor_str = parts[1]
    
    try:
        minor_val = int(minor_str)
        new_minor_val = minor_val + 1
        
        # Determine padding based on the original string
        if len(minor_str) >= 2 and minor_str.startswith('0'):
             new_minor_str = f"{new_minor_val:02d}"
        else:
             new_minor_str = str(new_minor_val)
             
        new_ver = f"{major}.{new_minor_str}"
    except ValueError:
        print("Could not parse minor version as integer.")
        return
    
    print(f"Bumping version: {current_ver} -> {new_ver}")
    
    files_changed = False
    for rel in FILES:
        path = os.path.join(base_dir, rel)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = f.read()
            
            # Replace logic:
            # 1. "Spine Sorter vCurrent" -> "Spine Sorter vNew" (Header/Window Title)
            # 2. APP_VERSION = "Current" -> APP_VERSION = "New" (Code Constant)
            
            new_data = data.replace(f"Spine Sorter v{current_ver}", f"Spine Sorter v{new_ver}")
            new_data = new_data.replace(f'APP_VERSION = "{current_ver}"', f'APP_VERSION = "{new_ver}"')
            
            if data != new_data:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_data)
                print(f"Updated {rel}")
                files_changed = True

    # 3. Create/Update version.txt in root
    version_file = os.path.join(workspace_root, "version.txt")
    with open(version_file, "w", encoding="utf-8") as vf:
        vf.write(new_ver)
    print(f"Updated version.txt to {new_ver}")
    
    if files_changed:
        print("Done.")

if __name__ == "__main__":
    bump()
