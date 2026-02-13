import re
import os
import sys

def detect_project_version(spine_path):
    print(f"Analyzing {spine_path}...")
    try:
        with open(spine_path, 'rb') as f:
            header = f.read(2048)
            decoded = header.decode('utf-8', errors='ignore')
            print(f"Decoded header start: {decoded[:100]}")
            
            # Pattern 1
            m = re.search(r'spine.*?([345]\.\d+(?:\.\d+)?)', decoded, re.IGNORECASE)
            if m: 
                print(f"Match 1 (spine...): {m.group(1)}")
                return m.group(1)
            
            # Pattern 2
            m = re.search(r'version.*?([345]\.\d+(?:\.\d+)?)', decoded, re.IGNORECASE)
            if m: 
                print(f"Match 2 (version...): {m.group(1)}")
                return m.group(1)

            # Pattern 3
            early_part = decoded[:100]
            m = re.search(r'\b([345]\.\d+(?:\.\d+)?)\b', early_part)
            if m: 
                print(f"Match 3 (early): {m.group(1)}")
                return m.group(1)
            
    except Exception as e:
        print(e)
    return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        detect_project_version(sys.argv[1])
    else:
        print("Usage: python debug_version.py <path_to_spine_file>")
