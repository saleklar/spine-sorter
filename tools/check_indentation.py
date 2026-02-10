import io,sys
p = r"z:\spine sorter v257\spine sorter 257.py"
start = 4600
end = 4700
with open(p,'rb') as f:
    lines=f.readlines()
for i in range(start-1, end):
    if i<0 or i>=len(lines): continue
    raw = lines[i]
    # show leading whitespace as escapes
    leading = raw[:len(raw)-len(raw.lstrip())]
    print(f"{i+1}: lead={leading!r} len={len(leading)} line={raw.decode('utf-8','replace').rstrip()}")
