"""Calibrate tile-SSIM gate: genuine rotated matches vs text false positives."""
import cv2, math, numpy as np
from skimage.metrics import structural_similarity as ssim

FOLDER = r"d:\shared drives\design\trailer_trash\04_animation\01_source\spine\images\win_events\png"
import os

def load_trimmed(path):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None: return None, None
    if img.shape[2] == 4:
        mask = (img[:, :, 3] > 10).astype(np.uint8) * 255
        ys, xs = np.where(mask > 0)
        y0, y1 = ys.min(), ys.max()+1; x0, x1 = xs.min(), xs.max()+1
        bgr = img[y0:y1, x0:x1, :3]; mask = mask[y0:y1, x0:x1]
        return cv2.bitwise_and(bgr, bgr, mask=mask), mask
    return img[:, :, :3], np.full(img.shape[:2], 255, np.uint8)

def match(small, large, flip=False):
    s_bgr, s_mask = load_trimmed(os.path.join(FOLDER, small))
    l_bgr, l_mask = load_trimmed(os.path.join(FOLDER, large))
    if flip: l_bgr = cv2.flip(l_bgr, 1); l_mask = cv2.flip(l_mask, 1)
    orb = cv2.ORB_create(nfeatures=800)
    kp1, des1 = orb.detectAndCompute(l_bgr, None)
    kp2, des2 = orb.detectAndCompute(s_bgr, None)
    if des1 is None or des2 is None: return None
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    ms = sorted(bf.match(des1, des2), key=lambda m: m.distance)[:120]
    if len(ms) < 8: return None
    src = np.float32([kp1[m.queryIdx].pt for m in ms]).reshape(-1,1,2)
    dst = np.float32([kp2[m.trainIdx].pt for m in ms]).reshape(-1,1,2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if M is None or inl is None or inl.sum() < 8: return None
    sh, sw = s_bgr.shape[:2]
    warp = cv2.warpAffine(l_bgr, M, (sw, sh))
    wmask = cv2.warpAffine(l_mask, M, (sw, sh), flags=cv2.INTER_NEAREST)
    common = cv2.bitwise_and(wmask, s_mask)
    cov = common.sum() / max(1, s_mask.sum())
    # histogram gate (same as app)
    s_c = cv2.bitwise_and(s_bgr, s_bgr, mask=common)
    w_c = cv2.bitwise_and(warp, warp, mask=common)
    hsv1 = cv2.cvtColor(s_c, cv2.COLOR_BGR2HSV); hsv2 = cv2.cvtColor(w_c, cv2.COLOR_BGR2HSV)
    h1 = cv2.calcHist([hsv1], [0,1], common, [180,256], [0,180,0,256])
    h2 = cv2.calcHist([hsv2], [0,1], common, [180,256], [0,180,0,256])
    cv2.normalize(h1, h1, 0, 1, cv2.NORM_MINMAX); cv2.normalize(h2, h2, 0, 1, cv2.NORM_MINMAX)
    hist_corr = cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)
    g1 = cv2.cvtColor(cv2.bitwise_and(s_bgr, s_bgr, mask=common), cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(cv2.bitwise_and(warp, warp, mask=common), cv2.COLOR_BGR2GRAY)
    global_ssim = ssim(g1, g2)
    # high-error blob analysis: different content -> large connected error blobs;
    # rotation resampling -> thin scattered edge noise
    diff = cv2.absdiff(g1, g2)
    diff[common == 0] = 0
    err = (diff > 48).astype(np.uint8)
    err = cv2.morphologyEx(err, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))  # kill thin edges
    n_lbl, lbl, stats_cc, _ = cv2.connectedComponentsWithStats(err, connectivity=8)
    content_px = max(1, int((common > 0).sum()))
    err_frac = err.sum() / content_px
    biggest_blob = (max(stats_cc[1:, cv2.CC_STAT_AREA]) / content_px) if n_lbl > 1 else 0.0
    # tile SSIM 4x4
    tiles = []
    th_, tw_ = sh // 4, sw // 4
    for ty in range(4):
        for tx in range(4):
            y0, y1 = ty*th_, (ty+1)*th_ if ty < 3 else sh
            x0, x1 = tx*tw_, (tx+1)*tw_ if tx < 3 else sw
            m = common[y0:y1, x0:x1]
            if m.size == 0: continue
            fill = (m > 0).mean()
            if fill < 0.15: continue  # tile mostly empty
            t1, t2 = g1[y0:y1, x0:x1], g2[y0:y1, x0:x1]
            if min(t1.shape) < 8: continue
            tiles.append(ssim(t1, t2))
    return cov, global_ssim, (min(tiles) if tiles else None), err_frac, biggest_blob, hist_corr

PAIRS = [
    # false positives (different text)
    ("trailer_txt_stroke.png", "kegger_txt_stroke.png", "FALSE"),
    ("kegger_txt_stroke.png", "cold_one_txt_stroke.png", "FALSE"),
    # remaining distinct caps — can they match with relaxed ssim?
    ("cold_one_bottle_cap2.png", "cold_one_bottle_cap3.png", "CAP"),
    ("cold_one_bottle_cap2.png", "cold_one_bottle_cap1.png", "CAP"),
    ("cold_one_bottle_cap2.png", "kegger_bottle_cap3.png", "CAP"),
    ("cold_one_bottle_cap2.png", "kegger_bottle_cap2.png", "CAP"),
    ("cold_one_bottle_cap3.png", "cold_one_bottle_cap1.png", "CAP"),
    ("cold_one_bottle_cap3.png", "kegger_bottle_cap3.png", "CAP"),
    ("cold_one_bottle_cap3.png", "kegger_bottle_cap2.png", "CAP"),
    ("cold_one_bottle_cap1.png", "kegger_bottle_cap2.png", "CAP"),
    ("cold_one_bottle_cap1.png", "kegger_bottle_cap3.png", "CAP"),
    ("kegger_bottle_cap3.png", "kegger_bottle_cap2.png", "CAP"),
    ("kegger_bottle_cap3.png", "kegger_bottle_cap1.png", "CAP"),
    ("kegger_bottle_cap5.png", "kegger_bottle_cap2.png", "CAP"),
]
for a, b, lbl in PAIRS:
    r = match(a, b)
    if r is None:
        r2 = match(a, b, flip=True)
        if r2 is None:
            print(f"{lbl:6} {a:28} vs {b:28} NO MATCH")
        else:
            cov, gs, mn, ef, bb, hc = r2
            print(f"{lbl:6} {a:28} vs {b:28} FLIP cov={cov:.2f} ssim={gs:.3f} errFrac={ef:.4f} hist={hc:.3f}")
    else:
        cov, gs, mn, ef, bb, hc = r
        print(f"{lbl:6} {a:28} vs {b:28}      cov={cov:.2f} ssim={gs:.3f} errFrac={ef:.4f} hist={hc:.3f}")
