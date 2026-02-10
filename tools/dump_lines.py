import sys
p = r"z:/spine sorter v257/spine sorter 257.py"
start = 4636
end = 4688
with open(p, 'rb') as f:
    lines = f.readlines()
for i in range(start-1, end):
    if i < 0 or i >= len(lines):
        continue
    raw = lines[i]
    # show leading whitespace as escapes
    print(f"{i+1}: {raw.decode('utf-8','replace').encode('unicode_escape').decode('ascii')}")
