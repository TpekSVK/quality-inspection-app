# core/tools/presence_absence.py
import cv2 as cv
import numpy as np
from typing import Dict, Tuple, Optional
from .base_tool import BaseTool, ToolResult

def _warp_roi(img: np.ndarray, H: Optional[np.ndarray], roi: Tuple[int,int,int,int]) -> np.ndarray:
    x, y, w, h = roi
    if H is not None:
        warped = cv.warpPerspective(img, H, (img.shape[1], img.shape[0]))
        return warped[y:y+h, x:x+w]
    else:
        return img[y:y+h, x:x+w]

class PresenceAbsenceTool(BaseTool):
    def run(self, img_ref: np.ndarray, img_cur: np.ndarray, fixture_transform: Optional[np.ndarray]) -> ToolResult:
        x, y, w, h = self.roi_xywh
        roi_cur = _warp_roi(img_cur, fixture_transform, (x,y,w,h))
        if roi_cur.ndim == 3: roi_cur = cv.cvtColor(roi_cur, cv.COLOR_BGR2GRAY)

        tpl = self.params.get("template", None)
        if tpl is None:
            roi_ref = _warp_roi(img_ref, fixture_transform, (x,y,w,h))
            if roi_ref.ndim == 3: roi_ref = cv.cvtColor(roi_ref, cv.COLOR_BGR2GRAY)
            tpl = roi_ref.copy()
        if tpl.ndim == 3: tpl = cv.cvtColor(tpl, cv.COLOR_BGR2GRAY)

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

        details = {"roi_xywh": (x,y,w,h), "score": measured, "minScore": minScore}
        return ToolResult(ok=ok, measured=measured, lsl=lsl, usl=usl, details=details, overlay=overlay)
