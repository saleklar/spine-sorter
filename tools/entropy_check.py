import math
samples = ['s5EgAaiNQm8','qTisLBz8h6o','GameIntro','REF']
for s in samples:
    counts={}
    for ch in s:
        counts[ch]=counts.get(ch,0)+1
    L=len(s)
    entropy=0.0
    for c in counts.values():
        p=c/L
        entropy -= p * math.log2(p)
    print(s, 'len=',L, 'entropy=', round(entropy,3))
