# Check why visually-different red ruby piles pass SSIM/error gates:
# dump trimmed sizes, and compare grayscale vs per-channel color diff on the
# aligned overlap of the 4 falsely-matching pairs.
import math, os, sys
import numpy as np
import cv2
from skimage.metrics import structural_similarity as ssim

sys.path.insert(0, os.path.dirname(__file__))
from diagnose_ruby_false_match import _sc_load_trimmed

FOLDER = r"D:\Shared drives\Design\Mr_Oinksters_Mummy_Mayhem\04_Animation\01_Source\Spine\images\persistence\png\red"
OUT = os.path.join(os.path.dirname(__file__), "ruby_diag")
os.makedirs(OUT, exist_ok=True)

for f in sorted(os.listdir(FOLDER)):
    if f.startswith("pile"):
        b, m = _sc_load_trimmed(os.path.join(FOLDER, f))
        print(f"{f}: trimmed {b.shape[1]}x{b.shape[0]}, content px={int((m>0).sum())}, "
              f"mean gray={cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)[m>0].mean():.1f}, "
              f"mean BGR={[round(float(b[:,:,c][m>0].mean()),1) for c in range(3)]}")

PAIRS = [("pile_l_3.png", "pile_l_4.png"),
         ("pile_l_3.png", "pile_r_3.png"),
         ("pile_l_3.png", "pile_r_4.png"),
         ("pile_l_4.png", "pile_r_4.png")]

for a, b in PAIRS:
    pa, pb = os.path.join(FOLDER, a), os.path.join(FOLDER, b)
    s_bgr, s_mask = _sc_load_trimmed(pa)
    l_bgr, l_mask = _sc_load_trimmed(pb)
    orb = cv2.ORB_create(nfeatures=800)
    kp1, des1 = orb.detectAndCompute(l_bgr, None)
    kp2, des2 = orb.detectAndCompute(s_bgr, None)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    ms = sorted(bf.match(des1, des2), key=lambda m: m.distance)[:120]
    src = np.float32([kp1[m.queryIdx].pt for m in ms]).reshape(-1, 1, 2)
    dst = np.float32([kp2[m.trainIdx].pt for m in ms]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    sh, sw = s_bgr.shape[:2]
    wb = cv2.warpAffine(l_bgr, M, (sw, sh))
    wm = cv2.warpAffine(l_mask, M, (sw, sh), flags=cv2.INTER_NEAREST)
    common = cv2.bitwise_and(wm, s_mask)
    g1 = cv2.cvtColor(cv2.bitwise_and(s_bgr, s_bgr, mask=common), cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(cv2.bitwise_and(wb, wb, mask=common), cv2.COLOR_BGR2GRAY)
    # gray diff stats
    dg = cv2.absdiff(g1, g2); dg[common == 0] = 0
    # per-channel color diff
    dc = cv2.absdiff(cv2.bitwise_and(s_bgr, s_bgr, mask=common),
                     cv2.bitwise_and(wb, wb, mask=common)).max(axis=2)
    dc[common == 0] = 0
    cpx = max(1, int((common > 0).sum()))
    print(f"\n{a} vs {b}:")
    print(f"  gray diff:  mean={dg[common>0].mean():.1f}  >48 frac={float((dg>48).sum())/cpx:.5f}")
    print(f"  color diff: mean={dc[common>0].mean():.1f}  >48 frac={float((dc>48).sum())/cpx:.5f}  >32 frac={float((dc>32).sum())/cpx:.5f}")
    em = (dc > 48).astype(np.uint8)
    em = cv2.morphologyEx(em, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _l, st, _c = cv2.connectedComponentsWithStats(em, connectivity=8)
    blob = float(st[1:, cv2.CC_STAT_AREA].max()) / cpx if n > 1 else 0.0
    print(f"  color err_frac(after open)={float(em.sum())/cpx:.5f} max_blob={blob:.5f}")
    # side-by-side visual
    vis = np.zeros((sh, sw * 3 + 20, 3), np.uint8)
    vis[:, :sw] = s_bgr
    vis[:, sw+10:sw*2+10] = wb
    heat = cv2.applyColorMap(cv2.normalize(dc, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8), cv2.COLORMAP_JET)
    heat[common == 0] = 0
    vis[:, sw*2+20:] = heat
    cv2.imwrite(os.path.join(OUT, f"cmp_{a[:-4]}_vs_{b[:-4]}.png"), vis)
print(f"\nComparisons saved to {OUT}")
