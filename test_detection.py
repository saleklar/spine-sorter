import re

def detect(header_bytes):
    try:
        decoded = header_bytes.decode('utf-8', errors='ignore')
        print(f"Decoded: {decoded}")
        
        # 1. spine...version
        m = re.search(r'spine.*?([345]\.\d+(?:\.\d+)?)', decoded, re.IGNORECASE)
        if m: return f"Match 1: {m.group(1)}"
        
        # 2. version...
        m = re.search(r'version.*?([345]\.\d+(?:\.\d+)?)', decoded, re.IGNORECASE)
        if m: return f"Match 2: {m.group(1)}"

        # 3. Two dots
        m = re.search(r'([345]\.\d+\.\d+)', decoded)
        if m: return f"Match 3: {m.group(1)}"

        # 4. Early part
        early_part = decoded[:100]
        m = re.search(r'\b([345]\.\d+(?:\.\d+)?)\b', early_part)
        if m: return f"Match 4: {m.group(1)}"
        
    except Exception as e:
        print(e)
    return None

# Test cases
cases = [
    b"spine 4.2.43 something",
    b"\x00\x00spine\x004.2.43\x00",
    b"random 4.2.43 data",
    b"version 4.1.24",
    b"\x004.2.43\x00", # Should match rule 3
    b"3.8.75",        # Should match rule 3 or 4
]

for c in cases:
    print(f"Input: {c} -> {detect(c)}")
