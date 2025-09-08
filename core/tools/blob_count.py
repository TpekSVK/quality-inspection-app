# core/tools/blob_count.py
import cv2 as cv
import numpy as np
from .base_tool import BaseTool, ToolResult

class BlobCountTool(BaseTool):
    """
    Počíta objekty (bloby) v ROI po predspracovaní.

    Params (t["params"]):
      - preproc: [... reťazec filtrov ...]
      - mask_rects: [[x,y,w,h], ...] ignorované oblasti (globálne ref súradnice)
      - min_area: int  (px²) – min plocha blobu
      - invert: bool  – invertovať po Otsu
      - metric: "count" | "sum_area" – čo ide do 'measured' (default: "count")
      - draw_contours: bool – ak True, vrátime kontúry v absolútnych súradniciach (pre RUN overlay)

    Výstup:
      - measured: podľa metric (count alebo sum_area)
      - details: pre RUN (preproc_desc, count, sum_area_px2, min_area, invert, binarize, metric, draw_contours, contours_abs)
    """
    TYPE = "blob_count"

    def run(self, img_ref, img_cur, fixture_transform=None) -> ToolResult:
        # 1) dorovnaj current do ref (aby ROI/masky sedeli 1:1)
        cur_aligned = self.align_current_to_ref(img_ref, img_cur, fixture_transform)
            

        # 2) bezpečné ROI
        x, y, w, h = [int(v) for v in self.roi_xywh]
        H, W = img_ref.shape[:2]
        x = max(0, min(x, W-1)); y = max(0, min(y, H-1))
        w = max(0, min(w, W - x)); h = max(0, min(h, H - y))
        if w <= 0 or h <= 0:
            return ToolResult(
                ok=True, measured=0.0, lsl=self.lsl, usl=self.usl,
                details={"error": "empty_roi"}, overlay=None
            )

        roi = cur_aligned[y:y+h, x:x+w]
        roi_gray = roi if roi.ndim == 2 else cv.cvtColor(roi, cv.COLOR_BGR2GRAY)

        # 3) maska do ROI-lokálnych súradníc
        params = dict(self.params or {})
        mask_rects = params.get("mask_rects", []) or []
        m = self.roi_mask_intersection(x, y, w, h, mask_rects, roi_shape=(h, w)) if mask_rects else None



        # 4) predspracovanie
        chain = params.get("preproc", []) or []
        roi_p = self._apply_preproc_chain(roi_gray, chain, mask=m)

        # 5) binarizácia (Otsu) + invert
        _th, bw = cv.threshold(roi_p, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
        if bool(params.get("invert", False)):
            bw = cv.bitwise_not(bw)
        if m is not None:
            bw = cv.bitwise_and(bw, bw, mask=m)

        # 6) kontúry a filtrovanie podľa min_area
        cnts, _ = cv.findContours(bw, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        min_area = int(params.get("min_area", 120))
        keep = [c for c in cnts if cv.contourArea(c) >= min_area]
        count = len(keep)
        sum_area = float(sum(cv.contourArea(c) for c in keep))

        # 7) metrika a OK/NOK
        metric = str(params.get("metric", "count")).lower()
        measured = float(count) if metric == "count" else float(sum_area)

        lsl, usl = self.lsl, self.usl
        ok = True
        if lsl is not None and measured < float(lsl): ok = False
        if usl is not None and measured > float(usl): ok = False

        # 8) kontúry do absolútnych súradníc (kvôli kresleniu)
        draw_contours = bool(params.get("draw_contours", False))
        contours_abs = None
        if draw_contours and keep:
            contours_abs = []
            for c in keep:
                ca = c.copy()
                ca[:,0,0] += x
                ca[:,0,1] += y
                contours_abs.append(ca)

        details = {
            "roi_xywh": (x, y, w, h),
            "mask_rects": mask_rects,
            "preproc_desc": self._preproc_desc(chain),
            "min_area": min_area,
            "invert": bool(params.get("invert", False)),
            "binarize": "otsu",
            "count": int(count),
            "sum_area_px2": float(sum_area),
            "metric": metric,
            "draw_contours": draw_contours,
            "contours_abs": contours_abs
        }


        return ToolResult(
            ok=ok, measured=measured, lsl=lsl, usl=usl,
            details=details, overlay=None
        )
