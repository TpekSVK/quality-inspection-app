# core/tools/diff_from_ref.py
import cv2 as cv
import numpy as np
from typing import Dict, Tuple, Optional
from .base_tool import BaseTool, ToolResult

def _safe_crop(img: np.ndarray, roi: Tuple[int,int,int,int]) -> np.ndarray:
    """Orež ROI tak, aby bol vždy vo vnútri obrázka (bez pádu)."""
    x, y, w, h = roi
    H, W = img.shape[:2]
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(W, x + w)
    y2 = min(H, y + h)
    if x2 <= x1 or y2 <= y1:
        return img[0:0, 0:0]  # prázdne
    return img[y1:y2, x1:x2]

def _warp_roi(img: np.ndarray, H: Optional[np.ndarray], roi: Tuple[int,int,int,int]) -> np.ndarray:
    """Ak máme H, narovnáme celý obrázok a potom bezpečne orežeme ROI."""
    if H is not None:
        warped = cv.warpPerspective(img, H, (img.shape[1], img.shape[0]))
        return _safe_crop(warped, roi)
    else:
        return _safe_crop(img, roi)

def _align_same_size(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Zarovná dve ROI na rovnaký rozmer odrezaním na spoločné minimum."""
    if a.size == 0 or b.size == 0:
        return a, b
    ha, wa = a.shape[:2]
    hb, wb = b.shape[:2]
    h = min(ha, hb)
    w = min(wa, wb)
    if h <= 0 or w <= 0:
        return a[0:0,0:0], b[0:0,0:0]
    return a[:h, :w], b[:h, :w]

class DiffFromRefTool(BaseTool):
    def run(self, img_ref: np.ndarray, img_cur: np.ndarray, fixture_transform: Optional[np.ndarray]) -> ToolResult:
        x, y, w, h = self.roi_xywh
        roi_ref = _warp_roi(img_ref, fixture_transform, (x,y,w,h))
        roi_cur = _warp_roi(img_cur, fixture_transform, (x,y,w,h))

        # prevedieme na 1-kanál
        if roi_ref.ndim == 3: roi_ref = cv.cvtColor(roi_ref, cv.COLOR_BGR2GRAY)
        if roi_cur.ndim == 3: roi_cur = cv.cvtColor(roi_cur, cv.COLOR_BGR2GRAY)

        # zarovnanie rozmerov (kvôli rozdielnym rozlíšeniam ref vs. RTSP)
        roi_ref, roi_cur = _align_same_size(roi_ref, roi_cur)

        # ak by ROI po orezaní vyšla prázdna → konfigurácia je mimo záberu
        if roi_ref.size == 0 or roi_cur.size == 0:
            details = {
                "roi_xywh": (x,y,w,h),
                "error": "ROI out of bounds for current/ref frame after clipping"
            }
            # nech je to NOK, aby to hneď upozornilo
            return ToolResult(ok=False, measured=0.0, lsl=self.lsl, usl=self.usl, details=details, overlay=None)

        blur = int(self.params.get("blur", 3))
        if blur > 0 and blur % 2 == 1:
            roi_ref = cv.GaussianBlur(roi_ref, (blur, blur), 0)
            roi_cur = cv.GaussianBlur(roi_cur, (blur, blur), 0)

        diff = cv.absdiff(roi_cur, roi_ref)

        thresh_val = int(self.params.get("thresh", 25))
        _, bw = cv.threshold(diff, thresh_val, 255, cv.THRESH_BINARY)

        morph_open = int(self.params.get("morph_open", 1))
        if morph_open > 0:
            k = cv.getStructuringElement(cv.MORPH_ELLIPSE, (3,3))
            bw = cv.morphologyEx(bw, cv.MORPH_OPEN, k, iterations=morph_open)

        num_labels, labels, stats, _ = cv.connectedComponentsWithStats(bw, connectivity=8)
        min_blob_area = int(self.params.get("min_blob_area", 20))
        areas = []
        kept_mask = np.zeros_like(bw)
        for lbl in range(1, num_labels):
            area = stats[lbl, cv.CC_STAT_AREA]
            if area >= min_blob_area:
                areas.append(area)
                kept_mask[labels == lbl] = 255

        total_area = float(np.sum(areas)) if areas else 0.0
        count = int(len(areas))

        measure_mode = self.params.get("measure", "area")
        measured = total_area if measure_mode == "area" else float(count)

        lsl, usl = self.lsl, self.usl
        ok = True
        if lsl is not None and measured < lsl: ok = False
        if usl is not None and measured > usl: ok = False

        overlay = cv.cvtColor(roi_cur, cv.COLOR_GRAY2BGR)
        overlay[kept_mask > 0] = (0, 0, 255)

        details = {
            "roi_xywh": (x,y,w,h),
            "total_blob_area_px": total_area,
            "blob_count": count,
            "thresh": thresh_val,
            "min_blob_area": min_blob_area,
            "aligned_roi_shape": overlay.shape[:2]
        }
        return ToolResult(ok=ok, measured=measured, lsl=lsl, usl=usl, details=details, overlay=overlay)
