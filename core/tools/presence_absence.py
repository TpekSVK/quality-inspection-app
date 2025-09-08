# core/tools/presence_absence.py
import cv2 as cv
import numpy as np
from typing import Dict, Tuple, Optional, List
from .base_tool import BaseTool, ToolResult

def _warp_roi(img: np.ndarray, H: Optional[np.ndarray], roi: Tuple[int,int,int,int]) -> np.ndarray:
    x, y, w, h = roi
    if H is not None:
        warped = cv.warpPerspective(img, H, (img.shape[1], img.shape[0]))
        return warped[y:y+h, x:x+w]
    else:
        return img[y:y+h, x:x+w]

def _mask_from_rects_ignore(full_shape: Tuple[int,int], rects: List[List[int]]) -> np.ndarray:
    H, W = full_shape
    m = np.full((H, W), 255, np.uint8)
    for r in rects or []:
        x,y,w,h = [int(v) for v in r]
        x1 = max(0, x); y1 = max(0, y)
        x2 = min(W, x+w); y2 = min(H, y+h)
        if x2 > x1 and y2 > y1:
            m[y1:y2, x1:x2] = 0
    return m

class PresenceAbsenceTool(BaseTool):
    USES_MASKS = True

    def run(self, img_ref: np.ndarray, img_cur: np.ndarray, fixture_transform: Optional[np.ndarray]) -> ToolResult:
        x, y, w, h = [int(v) for v in self.roi_xywh]

        # zarovnanie jednotne cez BaseTool helper
        cur_aligned = self.align_current_to_ref(img_ref, img_cur, fixture_transform)


        roi_cur = cur_aligned[y:y+h, x:x+w]
        if roi_cur.ndim == 3:
            roi_cur = cv.cvtColor(roi_cur, cv.COLOR_BGR2GRAY)
        # šablóna – z params alebo z ROI referencie
        tpl = self.params.get("template", None)
        if tpl is None:
            roi_ref = img_ref[y:y+h, x:x+w]
            if roi_ref.ndim == 3:
                roi_ref = cv.cvtColor(roi_ref, cv.COLOR_BGR2GRAY)
            tpl = roi_ref.copy()
        if tpl.ndim == 3:
            tpl = cv.cvtColor(tpl, cv.COLOR_BGR2GRAY)

        # masky (ignorovať časti)
        mask_rects = (self.params or {}).get("mask_rects", []) or []
        full_mask = self.roi_mask_intersection(x, y, w, h, mask_rects, roi_shape=roi_cur.shape) if mask_rects else None


        # predspracovanie (rovnako na tpl aj cur), rešpektuj masku
        pre_desc = "—"
        pre_preview = None
        chain = (self.params or {}).get("preproc", []) or []
        if chain:
            roi_cur = self._apply_preproc_chain(roi_cur, chain, mask=full_mask)
            tpl     = self._apply_preproc_chain(tpl,     chain, mask=full_mask)
            pre_desc = self._preproc_desc(chain)
            pre_preview = cv.cvtColor(roi_cur, cv.COLOR_GRAY2BGR)


        # template match
        method = self.params.get("method", cv.TM_CCOEFF_NORMED)
        res = cv.matchTemplate(roi_cur, tpl, method)
        min_val, max_val, min_loc, max_loc = cv.minMaxLoc(res)
        score = max_val if method != cv.TM_SQDIFF_NORMED else (1.0 - min_val)

        minScore = float(self.params.get("minScore", 0.7))
        measured = float(score)
        lsl, usl = self.lsl, self.usl
        ok = measured >= minScore

        overlay = cv.cvtColor(roi_cur, cv.COLOR_GRAY2BGR)
        h_t, w_t = tpl.shape[:2]
        top_left = max_loc if method != cv.TM_SQDIFF_NORMED else min_loc
        cv.rectangle(overlay, top_left, (top_left[0]+w_t, top_left[1]+h_t), (0,255,0) if ok else (0,0,255), 2)

        details = {"roi_xywh": (x,y,w,h), "mask_rects": mask_rects, "score": measured, "minScore": minScore}
        details["preproc_desc"] = pre_desc
        details["preproc_preview"] = pre_preview


        return ToolResult(ok=ok, measured=measured, lsl=lsl, usl=usl, details=details, overlay=overlay)
