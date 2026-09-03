# Visual side-by-side + aligned diff for green/purple pile l/r pairs that still match.
import math, os, sys
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(__file__))
from verify_bruteforce_rotation import _sc_load_trimmed

BASE = r"D:\Shared drives\Design\Mr_Oinksters_Mummy_Mayhem\04_Animation\01_Source\Spine\images\persistence\png"
OUT = os.path.join(os.path.dirname(__file__), "ruby_diag")
os.makedirs(OUT, exist_ok=True)

PAIRS = [
    ("green", "pile_l_3.png", "pile_r_3.png"),
    ("green", "pile_l_4.png", "pile_r_4.png"),
    ("purple", "pile_l_3.png", "pile_r_3.png"),
    ("purple", "pile_l_4.png", "pile_r_4.png"),
    ("red", "pile_l_3.png", "pile_r_3.png"),
    ("red", "pile_l_4.png", "pile_r_4.png"),
]

for color, a, b in PAIRS:
    fol = os.path.join(BASE, color)
    s_bgr, s_mask = _sc_load_trimmed(os.path.join(fol, a))
    l_bgr, l_mask = _sc_load_trimmed(os.path.join(fol, b))
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
    common_er = cv2.erode(common, np.ones((5, 5), np.uint8))
    b1 = cv2.GaussianBlur(s_bgr, (0, 0), 2.0)
    b2 = cv2.GaussianBlur(wb, (0, 0), 2.0)
    dc = cv2.absdiff(b1, b2).max(axis=2).astype(np.float32)
    dc[common_er == 0] = 0
    er_px = max(1, int((common_er > 0).sum()))
    print(f"{color}/{a} vs {b}: blur_mean={dc[common_er>0].mean():.2f} f24={float((dc>24).sum())/er_px:.4f}")
    vis = np.zeros((sh, sw * 3 + 20, 3), np.uint8)
    vis[:, :sw] = s_bgr
    vis[:, sw+10:sw*2+10] = wb
    heat = cv2.applyColorMap(np.clip(dc * 4, 0, 255).astype(np.uint8), cv2.COLORMAP_JET)
    heat[common_er == 0] = 0
    vis[:, sw*2+20:] = heat
    cv2.imwrite(os.path.join(OUT, f"{color}_{a[:-4]}_vs_{b[:-4]}.png"), vis)
print(f"saved to {OUT}")
