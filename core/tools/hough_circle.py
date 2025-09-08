# core/tools/hough_circle.py
import cv2 as cv
import numpy as np
from .base_tool import BaseTool, ToolResult

def _apply_mask_intersection(x, y, w, h, mask_rects, roi_shape):
    if not mask_rects:
        return None
    H, W = roi_shape[:2]
    m = np.full((H, W), 255, np.uint8)
    for (rx, ry, rw, rh) in mask_rects:
        Lx = max(x, int(rx)); Ly = max(y, int(ry))
        Rx = min(x + w, int(rx) + int(rw)); Ry = min(y + h, int(ry) + int(rh))
        if Rx > Lx and Ry > Ly:
            fx = Lx - x; fy = Ly - y; fw = Rx - Lx; fh = Ry - Ly
            m[fy:fy+fh, fx:fx+fw] = 0
    return m

def _apply_preproc_chain(gray_roi: np.ndarray, chain: list, mask: np.ndarray=None) -> np.ndarray:
    img = gray_roi.copy()
    def blend(tmp):
        if mask is None: return tmp
        return np.where(mask > 0, tmp, img)
    for st in (chain or []):
        try:
            op = str(st.get("op","")).lower()
            if op == "median":
                k = int(st.get("k",3)); k = k if k%2==1 else k+1
                img = blend(cv.medianBlur(img, max(1,k)))
            elif op == "gaussian":
                k = int(st.get("k",3)); k = k if k%2==1 else k+1
                img = blend(cv.GaussianBlur(img, (max(1,k),max(1,k)), 0))
            elif op == "clahe":
                clip=float(st.get("clip",2.0)); tile=int(st.get("tile",8))
                clahe = cv.createCLAHE(clipLimit=max(0.1,clip), tileGridSize=(max(1,tile),max(1,tile)))
                img = blend(clahe.apply(img))
            elif op == "tophat":
                k = int(st.get("k",15)); k = k if k%2==1 else k+1
                se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k,k))
                img = blend(cv.morphologyEx(img, cv.MORPH_TOPHAT, se))
            elif op == "blackhat":
                k = int(st.get("k",15)); k = k if k%2==1 else k+1
                se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k,k))
                img = blend(cv.morphologyEx(img, cv.MORPH_BLACKHAT, se))
        except Exception:
            continue
    return img

class HoughCircleTool(BaseTool):
    """
    Hough Circle:
      - Hľadá kruhy v ROI (po preproc).
      - Parametre: dp, minDist, param1, param2, minRadius, maxRadius
      - Metrika: počet kruhov (ks).
    """
    def run(self, img_ref, img_cur, fixture_transform=None):
        x, y, w, h = [int(v) for v in self.roi_xywh]

        # dorovnaj current na referenciu
        img_cur = self.align_current_to_ref(img_ref, img_cur, fixture_transform)

        Hc, Wc = img_ref.shape[:2]
        x = max(0, min(x, Wc-1)); y = max(0, min(y, Hc-1))
        w = max(1, min(w, Wc - x)); h = max(1, min(h, Hc - y))


        p = dict(self.params or {})
        dp        = float(p.get("dp", 1.2))
        minDist   = float(p.get("minDist", 12.0))
        param1    = float(p.get("param1", 100.0))
        param2    = float(p.get("param2", 30.0))
        minR      = int(p.get("minRadius", 0))
        maxR      = int(p.get("maxRadius", 0))
        chain     = p.get("preproc", []) or []
        mask_rects= p.get("mask_rects", []) or []

        roi = img_cur[y:y+h, x:x+w]
        m = self.roi_mask_intersection(x, y, w, h, mask_rects, roi_shape=roi.shape) if mask_rects else None
        roi_p = self._apply_preproc_chain(roi, chain, mask=m)


        # HoughCircles potrebuje jemný blur
        try:
            work = cv.GaussianBlur(roi_p, (3,3), 1.0)
        except Exception:
            work = roi_p

        circles = cv.HoughCircles(
            work, cv.HOUGH_GRADIENT,
            dp=dp, minDist=max(1.0, minDist),
            param1=max(1.0, param1), param2=max(1.0, param2),
            minRadius=max(0, minR), maxRadius=max(0, maxR)
        )

        overlay = cv.cvtColor(roi_p, cv.COLOR_GRAY2BGR)
        cnt = 0
        if circles is not None and len(circles) > 0:
            circles = np.round(circles[0, :]).astype(int)
            cnt = int(len(circles))
            for (cx,cy,rr) in circles:
                if cx<0 or cy<0 or cx>=w or cy>=h: 
                    continue
                cv.circle(overlay, (cx,cy), rr, (0,200,0), 2, cv.LINE_AA)
                cv.circle(overlay, (cx,cy), 2, (0,200,0), 2, cv.LINE_AA)

        measured = float(cnt)

        # OK/NOK vyhodnotenie lokálne cez LSL/USL
        lsl, usl = self.lsl, self.usl
        ok_flag = True
        if lsl is not None and measured < float(lsl): ok_flag = False
        if usl is not None and measured > float(usl): ok_flag = False

        details = {
            "roi_xywh": [x,y,w,h],
            "mask_rects": mask_rects,
            "preproc_desc": self._preproc_desc(chain),
            "preproc_preview": roi_p.copy(),
            "dp": dp, "minDist": minDist, "param1": param1, "param2": param2,
            "minRadius": minR, "maxRadius": maxR,
            "count": cnt
        }

        return ToolResult(
            ok=ok_flag,
            measured=measured,
            lsl=self.lsl,
            usl=self.usl,
            details=details,
            overlay=overlay
        )


