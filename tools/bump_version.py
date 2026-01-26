import os
import re
import sys

# Define the regex to find the version string "Spine Sorter vX.XX"
VERSION_REGEX = r"Spine Sorter v(\d+\.\d+)"

# Files relative to this script (tools/bump_version.py)
FILES = [
    "../spine sorter 257.py",
    "../Spine Sorter 257.spec",
    "../build_mac.sh"
]

def bump():
    # Get the directory where this script sits (tools/)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Read current version from the main python file
    main_file = os.path.join(base_dir, FILES[0])
    if not os.path.exists(main_file):
        print(f"Error: {main_file} not found.")
        return

    with open(main_file, 'r', encoding='utf-8') as f:
        content = f.read()
        
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
        # If it was "04" (len 2, starts with 0), pad to "05"
        # If it was "4" (len 1), bump to "5" (no padding unless it was required)
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
            
            # Replace all occurrences of "Spine Sorter vCurrent" with "Spine Sorter vNew"
            new_data = data.replace(f"Spine Sorter v{current_ver}", f"Spine Sorter v{new_ver}")
            
            if data != new_data:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_data)
                print(f"Updated {rel}")
                files_changed = True
    
    if files_changed:
        print("Done.")

if __name__ == "__main__":
    bump()
