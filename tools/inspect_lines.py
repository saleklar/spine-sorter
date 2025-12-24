import sys
p = r'z:/spine sorter v257/spine sorter 257.py'
start = int(sys.argv[1]) if len(sys.argv) > 1 else 1108
end = int(sys.argv[2]) if len(sys.argv) > 2 else 1120
with open(p, 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i in range(start-1, min(end, len(lines))):
    print(f"{i+1}: {repr(lines[i])}")
