# core/tools/diff_from_ref.py
import cv2 as cv
import numpy as np
from typing import Tuple, Optional, List
from .base_tool import BaseTool, ToolResult

def _safe_crop(img: np.ndarray, roi: Tuple[int,int,int,int]) -> np.ndarray:
    x, y, w, h = roi
    H, W = img.shape[:2]
    x1 = max(0, x); y1 = max(0, y)
    x2 = min(W, x + w); y2 = min(H, y + h)
    if x2 <= x1 or y2 <= y1:
        return img[0:0, 0:0]
    return img[y1:y2, x1:x2]

def _warp_to_ref(img_cur: np.ndarray, img_ref_shape: Tuple[int,int], H: Optional[np.ndarray]) -> np.ndarray:
    """Vždy pracujeme v súradniciach referencie (rovnaký rozmer)."""
    ref_h, ref_w = img_ref_shape
    if H is not None:
        return cv.warpPerspective(img_cur, H, (ref_w, ref_h))
    return cv.resize(img_cur, (ref_w, ref_h), interpolation=cv.INTER_LINEAR)

def _align_same_size(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    if a.size == 0 or b.size == 0:
        return a, b
    ha, wa = a.shape[:2]; hb, wb = b.shape[:2]
    h = min(ha, hb); w = min(wa, wb)
    if h <= 0 or w <= 0:
        return a[0:0,0:0], b[0:0,0:0]
    return a[:h, :w], b[:h, :w]

def _mask_from_rects_ignore(full_shape: Tuple[int,int], rects: List[List[int]]) -> np.ndarray:
    """
    Vytvor binárnu masku pre OPERÁCIU bitwise_and:
      255 = ponechaj / analyzuj
        0 = IGNORUJ (vypni)
    rects = ZOZNAM OBLASTÍ, KTORÉ SA IGNORUJÚ (t.j. nastavíme na 0).
    """
    H, W = full_shape
    m = np.full((H, W), 255, np.uint8)  # default = analyzovať všetko
    for r in rects or []:
        x,y,w,h = [int(v) for v in r]
        x1 = max(0, x); y1 = max(0, y)
        x2 = min(W, x+w); y2 = min(H, y+h)
        if x2 > x1 and y2 > y1:
            m[y1:y2, x1:x2] = 0        # tieto oblasti IGNORUJ
    return m

def _load_mask(mask_path: Optional[str]) -> Optional[np.ndarray]:
    if not mask_path: return None
    m = cv.imread(mask_path, cv.IMREAD_GRAYSCALE)
    if m is None: return None
    _, m = cv.threshold(m, 1, 255, cv.THRESH_BINARY)
    return m

class DiffFromRefTool(BaseTool):
    def run(self, img_ref: np.ndarray, img_cur: np.ndarray, fixture_transform: Optional[np.ndarray]) -> ToolResult:
        # 1) do rozmeru referencie
        ref_gray = cv.cvtColor(img_ref, cv.COLOR_BGR2GRAY) if img_ref.ndim == 3 else img_ref
        cur_to_ref = _warp_to_ref(img_cur, ref_gray.shape[:2], fixture_transform)
        cur_gray = cv.cvtColor(cur_to_ref, cv.COLOR_BGR2GRAY) if cur_to_ref.ndim == 3 else cur_to_ref

        # 2) maska: mask_rects = IGNOROVAŤ tieto obdĺžniky
        params = self.params or {}
        mask_rects = params.get("mask_rects", []) or []
        mask_path = params.get("mask_path", None)

        if mask_rects:
            mask_full = _mask_from_rects_ignore(ref_gray.shape[:2], mask_rects)
        else:
            mask_full = _load_mask(mask_path)
            if mask_full is not None and mask_full.shape[:2] != ref_gray.shape[:2]:
                mask_full = None
        if mask_full is None:
            mask_full = np.full(ref_gray.shape[:2], 255, np.uint8)

        # 3) ROI v referenčných súradniciach
        x, y, w, h = self.roi_xywh
        roi_ref  = _safe_crop(ref_gray, (x,y,w,h))
        roi_cur  = _safe_crop(cur_gray, (x,y,w,h))
        roi_mask = _safe_crop(mask_full, (x,y,w,h))

        roi_ref, roi_cur = _align_same_size(roi_ref, roi_cur)
        roi_mask, _      = _align_same_size(roi_mask, roi_cur)

        if roi_ref.size == 0 or roi_cur.size == 0 or roi_mask.size == 0:
            details = {"roi_xywh": (x,y,w,h), "error": "ROI out of bounds after clipping"}
            return ToolResult(ok=False, measured=0.0, lsl=self.lsl, usl=self.usl, details=details, overlay=None)

        # 4) Predspracovanie (rovnaké na REF aj CUR), rešpektuje masku (0=ignoruj)
        chain = params.get("preproc", []) or []
        if chain:
            roi_ref = self._apply_preproc_chain(roi_ref, chain, mask=roi_mask)
            roi_cur = self._apply_preproc_chain(roi_cur, chain, mask=roi_mask)

        # 5) aplikuj masku (nulujeme ignorované oblasti pre diff)
        roi_ref = cv.bitwise_and(roi_ref, roi_mask)
        roi_cur = cv.bitwise_and(roi_cur, roi_mask)

        # 6) diff + prahovanie
        blur = int(params.get("blur", 3))
        if blur > 0 and blur % 2 == 1:
            roi_ref = cv.GaussianBlur(roi_ref, (blur, blur), 0)
            roi_cur = cv.GaussianBlur(roi_cur, (blur, blur), 0)


        diff = cv.absdiff(roi_cur, roi_ref)
        thresh_val = int(params.get("thresh", 25))
        _, bw = cv.threshold(diff, thresh_val, 255, cv.THRESH_BINARY)

        morph_open = int(params.get("morph_open", 1))
        if morph_open > 0:
            k = cv.getStructuringElement(cv.MORPH_ELLIPSE, (3,3))
            bw = cv.morphologyEx(bw, cv.MORPH_OPEN, k, iterations=morph_open)

        num_labels, labels, stats, _ = cv.connectedComponentsWithStats(bw, connectivity=8)
        min_blob_area = int(params.get("min_blob_area", 20))
        areas = []
        kept_mask = np.zeros_like(bw)
        for lbl in range(1, num_labels):
            area = stats[lbl, cv.CC_STAT_AREA]
            if area >= min_blob_area:
                areas.append(area)
                kept_mask[labels == lbl] = 255

        total_area = float(np.sum(areas)) if areas else 0.0
        count = int(len(areas))
        measured = total_area if params.get("measure","area") == "area" else float(count)

        ok = True
        if self.lsl is not None and measured < self.lsl: ok = False
        if self.usl is not None and measured > self.usl: ok = False

        overlay = cv.cvtColor(roi_cur, cv.COLOR_GRAY2BGR)
        overlay[kept_mask > 0] = (0, 0, 255)

        details = {
            "roi_xywh": (x,y,w,h),
            "total_blob_area_px": total_area,
            "blob_count": count,
            "thresh": thresh_val,
            "min_blob_area": min_blob_area,
            "mask_rects": mask_rects,
            "used_mask_path": (mask_path if mask_path else None)
        }
        return ToolResult(ok=ok, measured=measured, lsl=self.lsl, usl=self.usl, details=details, overlay=overlay)
