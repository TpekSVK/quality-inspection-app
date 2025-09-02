# core/tools/diff_from_ref.py
import cv2 as cv
import numpy as np
from typing import Dict, Tuple, Optional
from .base_tool import BaseTool, ToolResult

def _warp_roi(img: np.ndarray, H: Optional[np.ndarray], roi: Tuple[int,int,int,int]) -> np.ndarray:
    x, y, w, h = roi
    if H is not None:
        # warpneme celú fotku, potom vystrihneme ROI
        warped = cv.warpPerspective(img, H, (img.shape[1], img.shape[0]))
        return warped[y:y+h, x:x+w]
    else:
        return img[y:y+h, x:x+w]

class DiffFromRefTool(BaseTool):
    """
    ELI5: Zoberieme ROI z referencie a z aktuálneho obrázka,
    spravíme rozdiel, prahovanie a spočítame plochu blobov (defektov) + počet.
    OK/NOK podľa LSL/USL (typicky USL na plochu blobov).
    params:
      - blur: int (Gauss blur kernel, napr. 3 alebo 5; 0 = vyp)
      - diff_mode: "abs"|"ssim" (zatím "abs" je dosť)
      - thresh: int (0..255) – binárny prah po dife
      - morph_open: int (iters) – odstránenie šumu
      - min_blob_area: int (px) – ignorovať malé bodky
    measured = total_blob_area (px) alebo count (dá sa prepnúť parametrom 'measure' = 'area'|'count')
    """

    def run(self, img_ref: np.ndarray, img_cur: np.ndarray, fixture_transform: Optional[np.ndarray]) -> ToolResult:
        x, y, w, h = self.roi_xywh
        roi_ref = _warp_roi(img_ref, fixture_transform, (x,y,w,h))
        roi_cur = _warp_roi(img_cur, fixture_transform, (x,y,w,h))

        if roi_ref.ndim == 3: roi_ref = cv.cvtColor(roi_ref, cv.COLOR_BGR2GRAY)
        if roi_cur.ndim == 3: roi_cur = cv.cvtColor(roi_cur, cv.COLOR_BGR2GRAY)

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

        # Limitné hodnoty
        lsl, usl = self.lsl, self.usl
        ok = True
        if lsl is not None and measured < lsl: ok = False
        if usl is not None and measured > usl: ok = False

        # overlay (len ROI) – namaľujeme červené miesta
        overlay = cv.cvtColor(roi_cur, cv.COLOR_GRAY2BGR)
        overlay[kept_mask > 0] = (0, 0, 255)

        details = {
            "total_blob_area_px": total_area,
            "blob_count": count,
            "thresh": thresh_val,
            "min_blob_area": min_blob_area
        }
        return ToolResult(ok=ok, measured=measured, lsl=lsl, usl=usl, details=details, overlay=overlay)
