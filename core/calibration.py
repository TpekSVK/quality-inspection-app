# core/calibration.py
import cv2 as cv
import numpy as np
from typing import Tuple, Optional, Dict

def calibrate_checkerboard(
    img_gray: np.ndarray,
    pattern_size: Tuple[int,int] = (7,7),
    square_size_mm: float = 5.0
) -> Dict[str,float]:
    """
    ELI5: nájdeme mriežku (7x7 vnútorných rohov). Z priemerných vzdialeností rohov
    spočítame mm_per_px v oboch smeroch. Pre priemyselné merania to stačí.
    """
    ok, corners = cv.findChessboardCorners(img_gray, pattern_size, flags=cv.CALIB_CB_ADAPTIVE_THRESH+cv.CALIB_CB_NORMALIZE_IMAGE)
    if not ok:
        raise RuntimeError("Checkerboard sa nenašiel.")

    corners = cv.cornerSubPix(img_gray, corners, (11,11), (-1,-1),
                              criteria=(cv.TERM_CRITERIA_EPS+cv.TERM_CRITERIA_MAX_ITER, 30, 0.1))
    corners = corners.reshape(-1,2)
    w, h = pattern_size
    # horizontálne a vertikálne kroky v px
    hori_dists, vert_dists = [], []
    for r in range(h):
        for c in range(w-1):
            i = r*w + c
            j = r*w + c + 1
            hori_dists.append(np.linalg.norm(corners[j]-corners[i]))
    for r in range(h-1):
        for c in range(w):
            i = r*w + c
            j = (r+1)*w + c
            vert_dists.append(np.linalg.norm(corners[j]-corners[i]))

    px_per_square_h = float(np.mean(hori_dists))
    px_per_square_v = float(np.mean(vert_dists))
    mm_per_px_x = square_size_mm / px_per_square_h
    mm_per_px_y = square_size_mm / px_per_square_v

    return {"mm_per_px_x": mm_per_px_x, "mm_per_px_y": mm_per_px_y}

def calibrate_two_points(
    pt1: Tuple[int,int], pt2: Tuple[int,int], real_mm: float
) -> Dict[str,float]:
    """
    ELI5: medzi dvoma bodmi v pixeloch zmeriame vzdialenosť -> vieme koľko mm je 1 px.
    """
    dist_px = float(np.hypot(pt2[0]-pt1[0], pt2[1]-pt1[1]))
    if dist_px <= 0:
        raise ValueError("Body sú rovnaké.")
    mm_per_px = real_mm / dist_px
    return {"mm_per_px_x": mm_per_px, "mm_per_px_y": mm_per_px}
