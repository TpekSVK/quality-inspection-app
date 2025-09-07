# core/vis/overlay.py
import numpy as np
import cv2 as cv

def compose_overlay(frame_gray: np.ndarray, ref_shape: tuple, out: dict, only_idx: int = None, view_mode: str = "standard") -> np.ndarray:
    """
    Zloží zobrazovaný obrázok: základ = frame_gray (resamplovaný na ref_shape),
    do ktorého sa pre vybraný nástroj(y) (only_idx) mieša polo-transparentná overlay
    v ROI + kreslia sa ROI rámiky (modrá) a masky (fialová).
    """
    h_ref, w_ref = ref_shape
    base = frame_gray
    if base is None or base.size == 0:
        base = np.zeros((h_ref, w_ref), np.uint8)
    elif base.shape[:2] != (h_ref, w_ref):
        base = cv.resize(base, (w_ref, h_ref), interpolation=cv.INTER_LINEAR)

    canvas = cv.cvtColor(base, cv.COLOR_GRAY2BGR)
    # ak chce užívateľ "čistý obraz", rovno vráť BGR bez overlayov
    if view_mode == "clean":
        return canvas


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
        ov = None
        if view_mode == "standard":
            ov = getattr(r, "overlay", None)
        elif view_mode == "roi_preproc":
            ov = details.get("preproc_preview", None)
        elif view_mode == "roi_raw":
            # vystrihni surové ROI z frame_gray a premeň na BGR
            try:
                if roi is None:
                    raise ValueError("roi is None")
                rx, ry, rw, rh = [int(v) for v in roi]
                rx = max(0, min(w_ref-1, rx)); ry = max(0, min(h_ref-1, ry))
                RW = min(rw, w_ref - rx); RH = min(rh, h_ref - ry)
                if RW > 0 and RH > 0:
                    raw_roi = frame_gray[ry:ry+RH, rx:rx+RW]
                    ov = cv.cvtColor(raw_roi, cv.COLOR_GRAY2BGR)
            except Exception:
                ov = None

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
            cv.rectangle(canvas, (x,y), (x+W, y+Hh), (255, 180, 0), 2)
            
            
            if view_mode == "inset_preproc":
            # -- PREPROC PREVIEW (ak je k dispozícii) --
                pre = details.get("preproc_preview", None)
                if pre is not None:
                    try:
                        # uisti sa, že je BGR
                        if pre.ndim == 2:
                            pre = cv.cvtColor(pre, cv.COLOR_GRAY2BGR)
                        # veľkosť náhľadu ~ 1/3 šírky ROI, minimálne 64 px
                        tw = max(64, int(W * 0.33))
                        th = int(pre.shape[0] * (tw / pre.shape[1]))
                        pre_small = cv.resize(pre, (tw, th), interpolation=cv.INTER_AREA)
                        # miesto: roh ROI s malým odsadením
                        px, py = x + 6, y + 6
                        # ohraničenie
                        cv.rectangle(canvas, (px-2, py-2), (px+tw+2, py+th+2), (255, 210, 0), 1)
                        # vlož
                        roi_dst = canvas[py:py+th, px:px+tw]
                        if roi_dst.shape[:2] == pre_small.shape[:2]:
                            canvas[py:py+th, px:px+tw] = pre_small
                        # štítok
                        cv.rectangle(canvas, (px-2, py-18), (px+72, py-2), (255,210,0), -1)
                        cv.putText(canvas, "PREPROC", (px+4, py-6), cv.FONT_HERSHEY_SIMPLEX, 0.4, (30,30,30), 1, cv.LINE_AA)
                    except Exception:
                        pass

        except Exception:
            # nech runtime nespadne kvôli zlej ROI
            continue

    return canvas
