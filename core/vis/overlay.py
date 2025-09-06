# core/vis/overlay.py
import numpy as np
import cv2 as cv

def compose_overlay(frame_gray: np.ndarray, ref_shape: tuple, out: dict, only_idx: int = None) -> np.ndarray:
    """
    Zloží zobrazovaný obrázok: základ = frame_gray (resamplovaný na ref_shape),
    do ktorého sa pre vybraný nástroj(y) (only_idx) mieša polo-transparentná overlay
    v ROI + kreslia sa ROI rámiky (oranžová) a masky (fialová).
    """
    h_ref, w_ref = ref_shape
    base = frame_gray
    if base is None or base.size == 0:
        base = np.zeros((h_ref, w_ref), np.uint8)
    elif base.shape[:2] != (h_ref, w_ref):
        base = cv.resize(base, (w_ref, h_ref), interpolation=cv.INTER_LINEAR)

    canvas = cv.cvtColor(base, cv.COLOR_GRAY2BGR)

    results = out.get("results", []) if isinstance(out, dict) else []
    for i, r in enumerate(results):
        if only_idx is not None and i != only_idx:
            continue

        details = getattr(r, "details", {}) if hasattr(r, "details") else {}
        # masky – fialové
        for rect in (details.get("mask_rects", []) or []):
            try:
                mx,my,mw,mh = map(int, rect)
                x1 = max(0, min(w_ref-1, mx))
                y1 = max(0, min(h_ref-1, my))
                x2 = max(0, min(w_ref,   mx+mw))
                y2 = max(0, min(h_ref,   my+mh))
                if x2 > x1 and y2 > y1:
                    cv.rectangle(canvas, (x1,y1), (x2,y2), (255, 0, 255), 2)
            except Exception:
                pass

        # overlay v ROI – oranžový rám + miešanie
        roi = details.get("roi_xywh", None)
        ov  = getattr(r, "overlay", None)
        if roi is None or ov is None:
            continue

        try:
            x, y, ww, hh = [int(v) for v in roi]
            x = max(0, min(w_ref-1, x)); y = max(0, min(h_ref-1, y))
            W = min(ww, w_ref - x); Hh = min(hh, h_ref - y)
            if W <= 0 or Hh <= 0:
                continue
            if ov.shape[1] != W or ov.shape[0] != Hh:
                ov = cv.resize(ov, (W, Hh), interpolation=cv.INTER_NEAREST)
            # miešanie
            canvas[y:y+Hh, x:x+W] = cv.addWeighted(canvas[y:y+Hh, x:x+W], 0.6, ov, 0.4, 0)
            # ROI rámik
            cv.rectangle(canvas, (x,y), (x+W, y+Hh), (0, 180, 255), 2)
        except Exception:
            # nech runtime nespadne kvôli zlej ROI
            continue

    return canvas
