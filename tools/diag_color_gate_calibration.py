# Measure COLOR-diff stats on the aligned overlap for known-TRUE matches (coins)
# to calibrate a color gate that rejects the ruby false pairs.
import math, os, sys
import numpy as np
import cv2
from skimage.metrics import structural_similarity as ssim

sys.path.insert(0, os.path.dirname(__file__))
from verify_bruteforce_rotation import _sc_load_trimmed

COINS = r"e:\blazing_bullets_hold_and_win\04_animation\02_render\consolidation test\images\skeleton\png"
TRUE_PAIRS = [
    ("coins_lvl_5_6.png", "coins_lvl_5_8.png", True),
    ("coins_lvl_5_7 copy5.png", "coins_lvl_5_7 copy2.png", True),
    ("coins_lvl_5_7.png", "coins_lvl_5_7 copy2.png", False),
    ("coins_lvl_5_7 copy3.png", "coins_lvl_5_7 copy4.png", True),
    ("coins_lvl_5_7 copy5.png", "coins_lvl_5_7.png", True),
]

def color_stats(small_path, large_path, flip):
    s_bgr, s_mask = _sc_load_trimmed(small_path)
    l_bgr, l_mask = _sc_load_trimmed(large_path)
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
    sh, sw = s_bgr.shape[:2]
    wb = cv2.warpAffine(l_bgr, M, (sw, sh))
    wm = cv2.warpAffine(l_mask, M, (sw, sh), flags=cv2.INTER_NEAREST)
    common = cv2.bitwise_and(wm, s_mask)
    # erode common by 1px to drop antialiased border pixels (resampling noise)
    common_e = cv2.erode(common, np.ones((3, 3), np.uint8))
    dc = cv2.absdiff(cv2.bitwise_and(s_bgr, s_bgr, mask=common),
                     cv2.bitwise_and(wb, wb, mask=common)).max(axis=2)
    cpx = max(1, int((common > 0).sum()))
    cpx_e = max(1, int((common_e > 0).sum()))
    dce = dc.copy(); dce[common_e == 0] = 0
    dc[common == 0] = 0
    return (dc[common > 0].mean(), float((dc > 32).sum()) / cpx,
            dce[common_e > 0].mean() if cpx_e > 1 else 0, float((dce > 32).sum()) / cpx_e)

print("TRUE matches (coins):")
for a, b, fl in TRUE_PAIRS:
    r = color_stats(os.path.join(COINS, a), os.path.join(COINS, b), fl)
    if r:
        print(f"  {a} <- {b} flip={fl}: color mean={r[0]:.1f} >32frac={r[1]:.4f}  | eroded: mean={r[2]:.1f} >32frac={r[3]:.4f}")

RUBY = r"D:\Shared drives\Design\Mr_Oinksters_Mummy_Mayhem\04_Animation\01_Source\Spine\images\persistence\png\red"
FALSE_PAIRS = [
    ("pile_l_3.png", "pile_l_4.png", False),
    ("pile_l_3.png", "pile_r_3.png", False),
    ("pile_l_3.png", "pile_r_4.png", False),
    ("pile_l_4.png", "pile_r_4.png", False),
]
print("\nFALSE matches (ruby piles):")
for a, b, fl in FALSE_PAIRS:
    r = color_stats(os.path.join(RUBY, a), os.path.join(RUBY, b), fl)
    if r:
        print(f"  {a} <- {b} flip={fl}: color mean={r[0]:.1f} >32frac={r[1]:.4f}  | eroded: mean={r[2]:.1f} >32frac={r[3]:.4f}")
