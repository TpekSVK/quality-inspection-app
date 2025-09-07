# core/tools/blob_count.py
import cv2 as cv
import numpy as np
from .base_tool import BaseTool, ToolResult

class BlobCountTool(BaseTool):
    """
    Počíta objekty (bloby) v ROI po predspracovaní.
    - Rešpektuje masky (mask_rects) – ignorované oblasti dávame na 0.
    - Binarizácia: Otsu (jednoduché a robustné).
    - Parametre:
        params = {
            "preproc": [...],     # reťazec filtrov (ako pri ostatných nástrojoch)
            "mask_rects": [...],  # ignorované obdĺžniky v globálnych (ref) súradniciach
            "min_area": 120,      # min. plocha blobu [px]
            "invert": False       # invertovať binárny obraz po Otsu
        }
    Výstup:
      measured = count (ks), units="ks"
    """
    TYPE = "blob_count"

    def run(self, img_ref, img_cur, fixture_transform=None) -> ToolResult:
        # 1) dorovnaj current do súradníc referencie (aby ROI/masky sedeli 1:1)
        if fixture_transform is not None:
            cur_aligned = cv.warpPerspective(img_cur, fixture_transform, (img_ref.shape[1], img_ref.shape[0]))
        elif img_cur.shape[:2] != img_ref.shape[:2]:
            cur_aligned = cv.resize(img_cur, (img_ref.shape[1], img_ref.shape[0]), interpolation=cv.INTER_LINEAR)
        else:
            cur_aligned = img_cur

        # 2) bezpečné ROI (clamp)
        x, y, w, h = [int(v) for v in self.roi_xywh]
        H, W = img_ref.shape[:2]
        x = max(0, min(x, W-1)); y = max(0, min(y, H-1))
        w = max(0, min(w, W - x)); h = max(0, min(h, H - y))
        if w <= 0 or h <= 0:
            return ToolResult(
                ok=True, measured=0.0, lsl=self.lsl, usl=self.usl,
                details={"error":"empty_roi"}, overlay=None
            )

        roi = cur_aligned[y:y+h, x:x+w]
        if roi.ndim == 3:
            roi_gray = cv.cvtColor(roi, cv.COLOR_BGR2GRAY)
        else:
            roi_gray = roi

        # 3) maska v ROI-lokálnych súradniciach
        params = self.params or {}
        mask_rects = params.get("mask_rects", []) or []
        m = None
        if mask_rects:
            m = np.full((h, w), 255, np.uint8)
            for (rx, ry, rw, rh) in mask_rects:
                fx = max(0, int(rx) - x); fy = max(0, int(ry) - y)
                fw = max(0, min(int(rw), w - fx)); fh = max(0, min(int(rh), h - fy))
                if fw > 0 and fh > 0:
                    m[fy:fy+fh, fx:fx+fw] = 0

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

        # 7) OK/NOK podľa limitov
        lsl, usl = self.lsl, self.usl
        ok = True
        if lsl is not None and float(count) < lsl: ok = False
        if usl is not None and float(count) > usl: ok = False

        details = {
            "preproc_desc": self._preproc_desc(chain),
            "min_area": min_area,
            "invert": bool(params.get("invert", False)),
            "binarize": "otsu"
        }

        return ToolResult(
            ok=ok, measured=float(count), lsl=lsl, usl=usl,
            details=details, overlay=None
        )
