# core/vis/overlay.py
import numpy as np
import cv2 as cv
from config import ui_style as UI

def _to_bgr(gray, ref_shape):
    h_ref, w_ref = ref_shape
    if gray is None or gray.size == 0:
        base = np.zeros((h_ref, w_ref), np.uint8)
    elif gray.shape[:2] != (h_ref, w_ref):
        base = cv.resize(gray, (w_ref, h_ref), interpolation=cv.INTER_LINEAR)
    else:
        base = gray
    return cv.cvtColor(base, cv.COLOR_GRAY2BGR)

def compose_overlay(frame_gray, ref_shape, out, only_idx=None, view_mode="standard"):
    """
    Jednotné renderovanie pre všetky nástroje a náhľady.
      - 'standard'   : čistý obraz + ROI/masky; žiadny preproc ani nálezový overlay.
      - 'roi_preproc': do ROI vložíme 'preproc_preview'; fallback: Tool.overlay; mimo ROI nič.
      - 'roi_raw'    : do ROI vložíme RAW obsah (bez preproc) na porovnanie.
      - 'clean'      : len čistý obraz (bez ROI/masky/overlay).
    """
    canvas = _to_bgr(frame_gray, ref_shape)
    h_ref, w_ref = ref_shape

    if view_mode == "clean":
        return canvas

    results = out.get("results", []) if isinstance(out, dict) else []
    idxs = range(len(results)) if (only_idx is None) else [only_idx]

    def paste_roi(dst, src, x, y, w, h):
        H, W = dst.shape[:2]
        x1 = max(0, x); y1 = max(0, y)
        x2 = min(W, x + w); y2 = min(H, y + h)
        if x2 <= x1 or y2 <= y1:
            return
        src_bgr = src if (src.ndim == 3) else cv.cvtColor(src, cv.COLOR_GRAY2BGR)
        src_c = src_bgr[0:(y2 - y1), 0:(x2 - x1)]
        if src_c.shape[:2] == dst[y1:y2, x1:x2].shape[:2]:
            dst[y1:y2, x1:x2] = src_c

    for i in idxs:
        if i < 0 or i >= len(results):
            continue
        r = results[i]
        details = getattr(r, "details", {}) or {}

        roi_xywh = details.get("roi_xywh") or [0, 0, 0, 0]
        try:
            x, y, w, h = [int(v) for v in roi_xywh]
        except Exception:
            x, y, w, h = 0, 0, 0, 0

        # 1) rámiky
        if w > 0 and h > 0:
            cv.rectangle(canvas, (x, y), (x + w, y + h), UI.ROI_BGR, UI.PEN_THICK, cv.LINE_AA)

        for mr in (details.get("mask_rects") or []):
            try:
                mx, my, mw, mh = [int(v) for v in mr]
            except Exception:
                continue
            x1 = max(0, mx); y1 = max(0, my)
            x2 = min(w_ref, mx + mw); y2 = min(h_ref, my + mh)
            if x2 > x1 and y2 > y1:
                cv.rectangle(canvas, (x1, y1), (x2, y2), UI.MASK_BGR, UI.PEN_THIN, cv.LINE_AA)

        # 2) obsah podľa view_mode
        if view_mode == "standard":
            continue

        if view_mode == "roi_raw":
            if w > 0 and h > 0:
                raw_src = _to_bgr(frame_gray, ref_shape)
                paste_roi(canvas, raw_src[y:y+h, x:x+w], x, y, w, h)
            continue

        if view_mode == "roi_preproc":
            ov = details.get("preproc_preview", None)
            if ov is None:
                ov = getattr(r, "overlay", None)
            if ov is not None and w > 0 and h > 0:
                paste_roi(canvas, ov, x, y, w, h)
            # prípadné kontúry/nálezy: zelená
            # for c in details.get("contours_abs", []) or []:
            #     cv.drawContours(canvas, [c], -1, UI.DETECT_BGR, UI.PEN_THIN, cv.LINE_AA)
            continue

    return canvas
