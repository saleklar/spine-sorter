import os, re, difflib
root = r"z:\spine sorter v257"
words = set()
# load naming file
p = os.path.join(root, 'naming_conventions', 'naming_conventions.txt')
if os.path.exists(p):
    with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
        txt = fh.read()
    for w in re.findall(r"[A-Za-z0-9_]{3,}", txt):
        words.add(w.lower())
# add ambient fallback
words.add('ambient')

spines = []
for dirpath, dirs, files in os.walk(root):
    for f in files:
        if f.lower().endswith('.spine'):
            spines.append(os.path.join(dirpath, f))

print(f'Found {len(spines)} .spine files')
for s in spines:
    base = os.path.splitext(os.path.basename(s))[0]
    low = base.lower()
    # split into tokens by non-alnum
    toks = re.findall(r"[A-Za-z0-9_]{3,}", low)
    for t in toks:
        if t in words:
            continue
        m = difflib.get_close_matches(t, list(words), n=1, cutoff=0.7)
        if m:
            print(f"File: {s}\n token '{t}' -> suggestion: {m[0]}\n")
