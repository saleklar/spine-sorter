import re, difflib, sys
p='test_files_from_collegues/me/anticipation.spine'
try:
    s=open(p,'rb').read()
except Exception as e:
    print('ERROR opening',p, e); sys.exit(2)
words=re.findall(rb"[A-Za-z]{4,}",s)
words={w.decode('ascii',errors='ignore').lower() for w in words}
common={'anticipation','anticipate','idle','walk','run','jump','attack','intro','open','close','blink'}
found=False
for w in sorted(words):
    m=difflib.get_close_matches(w, common, n=1, cutoff=0.8)
    if m:
        print(w,'->',m[0])
        found=True
if not found:
    print('No fuzzy matches found')
