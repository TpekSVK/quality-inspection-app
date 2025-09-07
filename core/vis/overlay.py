# core/vis/overlay.py
import numpy as np
import cv2 as cv

def compose_overlay(frame_gray: np.ndarray, ref_shape: tuple, out: dict,
                    only_idx: int = None, view_mode: str = "standard") -> np.ndarray:
    """
    Zloží zobrazovaný obrázok.
      base = frame_gray (dorovnaný na ref_shape)
      - 'standard'  : len rámiky ROI + masky (ŽIADNE tool overlay lepenie)
      - 'roi_preproc': ak nástroj poslal 'preproc_preview', vloží ho do ROI; inak fallback na Tool.overlay
      - 'roi_raw'   : vloží RAW ROI (bez preproc) pre vybraný nástroj
      - 'clean'     : nič nekreslí (len base)
    """
    h_ref, w_ref = ref_shape
    base = frame_gray
    if base is None or base.size == 0:
        base = np.zeros((h_ref, w_ref), np.uint8)
    elif base.shape[:2] != (h_ref, w_ref):
        base = cv.resize(base, (w_ref, h_ref), interpolation=cv.INTER_LINEAR)

    canvas = cv.cvtColor(base, cv.COLOR_GRAY2BGR)

    results = out.get("results", []) if isinstance(out, dict) else []
    idxs = range(len(results)) if (only_idx is None) else [only_idx]

    for i in idxs:
        if i < 0 or i >= len(results):
            continue
        r = results[i]
        details = getattr(r, "details", {}) or {}

        # --- ROI rámik (modrý) ---
        try:
            x, y, w, h = [int(v) for v in (details.get("roi_xywh") or (0,0,0,0))]
            if w > 0 and h > 0:
                cv.rectangle(canvas, (x, y), (x+w, y+h), (255, 0, 0), 2, cv.LINE_AA)
        except Exception:
            pass

        # --- Masky (fialové obrysy) ---
        try:
            for (mx, my, mw, mh) in (details.get("mask_rects") or []):
                mx, my, mw, mh = int(mx), int(my), int(mw), int(mh)
                x1 = max(0, mx); y1 = max(0, my)
                x2 = min(w_ref, mx+mw); y2 = min(h_ref, my+mh)
                if x2 > x1 and y2 > y1:
                    cv.rectangle(canvas, (x1,y1), (x2,y2), (255, 0, 255), 2, cv.LINE_AA)
        except Exception:
            pass

        # --- Lepenie obsahu do ROI podľa view_mode ---
        if view_mode == "roi_preproc":
            # preferuj preproc_preview (grey→BGR), inak fallback na Tool.overlay
            ov = details.get("preproc_preview", None)
            if ov is not None:
                ov_bgr = ov if (ov.ndim == 3) else cv.cvtColor(ov, cv.COLOR_GRAY2BGR)
            else:
                ov = getattr(r, "overlay", None)
                ov_bgr = ov if (ov is not None) else None

            if ov_bgr is not None and w > 0 and h > 0:
                # bezpečné vloženie do ROI
                Hc, Wc = canvas.shape[:2]
                x1 = max(0, x); y1 = max(0, y)
                x2 = min(Wc, x+w); y2 = min(Hc, y+h)
                roi_dst = canvas[y1:y2, x1:x2]
                ov_res = ov_bgr[0:(y2-y1), 0:(x2-x1)]
                if roi_dst.shape[:2] == ov_res.shape[:2]:
                    canvas[y1:y2, x1:x2] = ov_res

        elif view_mode == "roi_raw":
            # vystrihni RAW ROI z base a vlož do canvas (pre vizuálne porovnanie)
            if w > 0 and h > 0:
                Hc, Wc = canvas.shape[:2]
                x1 = max(0, x); y1 = max(0, y)
                x2 = min(Wc, x+w); y2 = min(Hc, y+h)
                if x2 > x1 and y2 > y1:
                    raw = base[y1:y2, x1:x2]
                    raw_bgr = cv.cvtColor(raw, cv.COLOR_GRAY2BGR)
                    canvas[y1:y2, x1:x2] = raw_bgr

        elif view_mode == "standard":
            # nič nevkladáme (žiadne overlay/preproc), len rámiky – presne to si chcel
            pass

        elif view_mode == "clean":
            # nič nekresliť – ale sem sa typicky ani nedostaneme, ak to rieši RunTab
            pass

    return canvas

