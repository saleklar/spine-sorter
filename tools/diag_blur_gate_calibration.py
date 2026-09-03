# Calibrate a BLURRED color-diff gate: resampling noise (true rotated/scaled
# copies) is high-frequency and vanishes under Gaussian blur; genuine content
# differences (different gem arrangements) are low-frequency and survive.
import math, os, sys
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(__file__))
from verify_bruteforce_rotation import _sc_load_trimmed

COINS = r"e:\blazing_bullets_hold_and_win\04_animation\02_render\consolidation test\images\skeleton\png"
RUBY = r"D:\Shared drives\Design\Mr_Oinksters_Mummy_Mayhem\04_Animation\01_Source\Spine\images\persistence\png\red"

TRUE_PAIRS = [
    (COINS, "coins_lvl_5_6.png", "coins_lvl_5_8.png", True),
    (COINS, "coins_lvl_5_7 copy5.png", "coins_lvl_5_7 copy2.png", True),
    (COINS, "coins_lvl_5_7.png", "coins_lvl_5_7 copy2.png", False),
    (COINS, "coins_lvl_5_7 copy3.png", "coins_lvl_5_7 copy4.png", True),
    (COINS, "coins_lvl_5_7 copy5.png", "coins_lvl_5_7.png", True),
]
FALSE_PAIRS = [
    (RUBY, "pile_l_3.png", "pile_l_4.png", False),
    (RUBY, "pile_l_3.png", "pile_r_3.png", False),
    (RUBY, "pile_l_3.png", "pile_r_4.png", False),
    (RUBY, "pile_l_4.png", "pile_r_4.png", False),
]

def stats(folder, a, b, flip):
    s_bgr, s_mask = _sc_load_trimmed(os.path.join(folder, a))
    l_bgr, l_mask = _sc_load_trimmed(os.path.join(folder, b))
    if flip:
        l_bgr = cv2.flip(l_bgr, 1); l_mask = cv2.flip(l_mask, 1)
    orb = cv2.ORB_create(nfeatures=800)
    kp1, des1 = orb.detectAndCompute(l_bgr, None)
    kp2, des2 = orb.detectAndCompute(s_bgr, None)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    ms = sorted(bf.match(des1, des2), key=lambda m: m.distance)[:120]
    src = np.float32([kp1[m.queryIdx].pt for m in ms]).reshape(-1, 1, 2)
    dst = np.float32([kp2[m.trainIdx].pt for m in ms]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if M is None:
        return None
    a_c, b_c = M[0, 0], M[1, 0]
    scale = math.hypot(a_c, b_c)
    sh, sw = s_bgr.shape[:2]
    wb = cv2.warpAffine(l_bgr, M, (sw, sh))
    wm = cv2.warpAffine(l_mask, M, (sw, sh), flags=cv2.INTER_NEAREST)
    common = cv2.bitwise_and(wm, s_mask)
    common_e = cv2.erode(common, np.ones((5, 5), np.uint8))
    cpx = max(1, int((common_e > 0).sum()))
    # blur both, then per-channel diff, only inside eroded common area
    b1 = cv2.GaussianBlur(s_bgr, (0, 0), 2.0)
    b2 = cv2.GaussianBlur(wb, (0, 0), 2.0)
    dc = cv2.absdiff(b1, b2).max(axis=2).astype(np.float32)
    dc[common_e == 0] = 0
    mean_d = dc[common_e > 0].mean()
    f24 = float((dc > 24).sum()) / cpx
    f32 = float((dc > 32).sum()) / cpx
    # blob analysis on blurred diff
    em = (dc > 32).astype(np.uint8)
    em = cv2.morphologyEx(em, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _l, st, _c = cv2.connectedComponentsWithStats(em, connectivity=8)
    blob = float(st[1:, cv2.CC_STAT_AREA].max()) / cpx if n > 1 else 0.0
    return scale, mean_d, f24, f32, blob

print("TRUE matches (must stay matched):")
for fol, a, b, fl in TRUE_PAIRS:
    r = stats(fol, a, b, fl)
    if r:
        print(f"  {a} <- {b}: scale={r[0]:.3f} blur_mean={r[1]:.2f} f24={r[2]:.4f} f32={r[3]:.4f} blob={r[4]:.5f}")

print("\nFALSE matches (must be rejected):")
for fol, a, b, fl in FALSE_PAIRS:
    r = stats(fol, a, b, fl)
    if r:
        print(f"  {a} <- {b}: scale={r[0]:.3f} blur_mean={r[1]:.2f} f24={r[2]:.4f} f32={r[3]:.4f} blob={r[4]:.5f}")
