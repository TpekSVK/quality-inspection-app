# core/tools/edge_trace.py
from typing import Dict, Any, Optional, Tuple
import numpy as np
import cv2 as cv
from .base_tool import BaseTool, ToolResult

# --- helpers ---

def _warp_to_ref(img: np.ndarray, ref_shape: Tuple[int,int], H: Optional[np.ndarray]) -> np.ndarray:
    h_ref, w_ref = ref_shape
    if H is not None:
        return cv.warpPerspective(img, H, (w_ref, h_ref))
    if img.shape[:2] != (h_ref, w_ref):
        return cv.resize(img, (w_ref, h_ref), interpolation=cv.INTER_LINEAR)
    return img

def _safe_crop(img: np.ndarray, roi: Tuple[int,int,int,int]) -> np.ndarray:
    x, y, w, h = [int(v) for v in roi]
    H, W = img.shape[:2]
    x1 = max(0, x); y1 = max(0, y)
    x2 = min(W, x + w); y2 = min(H, y + h)
    if x2 <= x1 or y2 <= y1:
        return img[0:0, 0:0]
    return img[y1:y2, x1:x2]

def _shape_to_roi_local(params: Dict[str, Any], roi_xywh: Tuple[int,int,int,int]) -> Dict[str, Any]:
    x0, y0, _, _ = [int(v) for v in roi_xywh]
    p = dict(params or {})
    s = p.get("shape", None)
    if s == "line":
        pts = p.get("pts", [])
        p["pts"] = [[int(px)-x0, int(py)-y0] for (px,py) in pts] if len(pts) == 2 else []
    elif s == "circle":
        if p.get("cx") is not None and p.get("cy") is not None:
            p["cx"] = int(p["cx"]) - x0
            p["cy"] = int(p["cy"]) - y0
        p["r"] = int(p.get("r", 0))
    elif s == "polyline":
        pts = p.get("pts", [])
        p["pts"] = [[int(px)-x0, int(py)-y0] for (px,py) in pts] if len(pts) >= 2 else []
    p["width"] = int(p.get("width", 3))
    return p

def _draw_shape_mask(h: int, w: int, params_local: Dict[str, Any]) -> np.ndarray:
    m = np.zeros((h, w), np.uint8)
    s = params_local.get("shape")
    width = max(1, min(255, int(params_local.get("width", 3))))
    if s == "line":
        pts = params_local.get("pts", [])
        if len(pts) == 2:
            (x1,y1),(x2,y2) = pts
            cv.line(m, (int(x1),int(y1)), (int(x2),int(y2)), 255, thickness=width, lineType=cv.LINE_AA)
    elif s == "circle":
        cx = params_local.get("cx"); cy = params_local.get("cy"); r = int(params_local.get("r", 0))
        if cx is not None and cy is not None and r > 0:
            cv.circle(m, (int(cx),int(cy)), r, 255, thickness=width, lineType=cv.LINE_AA)
    elif s == "polyline":
        pts = params_local.get("pts", [])
        if len(pts) >= 2:
            arr = np.array([[int(x),int(y)] for (x,y) in pts], dtype=np.int32)
            cv.polylines(m, [arr], False, 255, thickness=width, lineType=cv.LINE_AA)
    return m

def _edge_stats(img_gray: np.ndarray, band_mask: np.ndarray,
                canny_lo: int, canny_hi: int) -> Dict[str, Any]:
    edges = cv.Canny(img_gray, canny_lo, canny_hi)
    band = (band_mask > 0)
    band_px = int(band.sum())
    edges_px = int((edges > 0)[band].sum())
    gap_px = max(0, band_px - edges_px)
    coverage_pct = (100.0 * edges_px / band_px) if band_px > 0 else 0.0

    # overlay: červený pás, zelené pixely = hrany v páse
    overlay = cv.cvtColor(img_gray, cv.COLOR_GRAY2BGR)
    overlay[band] = (0, 0, 255)
    green = (edges > 0) & band
    overlay[green] = (0, 255, 0)

    return {
        "band_px": band_px,
        "edges_px": edges_px,
        "gap_px": gap_px,
        "coverage_pct": float(coverage_pct),
        "overlay": overlay,
    }

# --- tools ---

class _EdgeTraceBase(BaseTool):
    def run(self, img_ref: np.ndarray, img_cur: np.ndarray, fixture_transform: Optional[np.ndarray]) -> ToolResult:
        if img_ref is None or img_cur is None or img_cur.size == 0:
            return ToolResult(False, 0.0, self.lsl, self.usl, {"error":"empty image", "roi_xywh": self.roi_xywh})

        # 1) Zarovnanie na referenciu
        cur_ref = _warp_to_ref(img_cur, img_ref.shape[:2], fixture_transform)
        if cur_ref.ndim == 3:
            cur_gray = cv.cvtColor(cur_ref, cv.COLOR_BGR2GRAY)
        else:
            cur_gray = cur_ref

        # 2) ROI crop
        x, y, w, h = [int(v) for v in self.roi_xywh]
        roi = (x, y, w, h)
        roi_gray = _safe_crop(cur_gray, roi)
        if roi_gray.size == 0:
            return ToolResult(False, 0.0, self.lsl, self.usl, {"error":"roi out of bounds", "roi_xywh": roi})

        # 3) Shape → ROI-lokálne súradnice
        p_global = dict(self.params or {})
        p_local = _shape_to_roi_local(p_global, roi)
        band = _draw_shape_mask(roi_gray.shape[0], roi_gray.shape[1], p_local)
        if band.sum() == 0:
            return ToolResult(False, 0.0, self.lsl, self.usl, {"error":"shape mask empty (nakresli tvar)", "roi_xywh": roi})

        # 4) Predspracovanie v ROI (len vnútri ROI; rešpektuj masky)
        pre_desc = "—"
        pre_preview = None

        # postav masku v rámci ROI (255 = analyzuj, 0 = ignoruj)
        full_mask = None
        mask_rects = (self.params or {}).get("mask_rects", []) or []
        if mask_rects:
            full_mask = np.full((h, w), 255, np.uint8)
            for (rx, ry, rw, rh) in mask_rects:
                fx = max(0, int(rx) - x)
                fy = max(0, int(ry) - y)
                fw = max(0, min(int(rw), w - fx))
                fh = max(0, min(int(rh), h - fy))
                if fw > 0 and fh > 0:
                    full_mask[fy:fy+fh, fx:fx+fw] = 0

        chain = p_global.get("preproc", []) or []
        if chain:
            roi_gray = self._apply_preproc_chain(roi_gray, chain, mask=full_mask)
            pre_desc = self._preproc_desc(chain)
            pre_preview = cv.cvtColor(roi_gray, cv.COLOR_GRAY2BGR)


        # 5) Metrika
        canny_lo = int(p_global.get("canny_lo", 40))
        canny_hi = int(p_global.get("canny_hi", 120))
        stats = _edge_stats(roi_gray, band, canny_lo, canny_hi)


        metric = str(p_global.get("metric", "px_gap")).lower()
        if metric == "coverage_pct":
            measured = float(stats["coverage_pct"])
        else:
            metric = "px_gap"
            measured = float(stats["gap_px"])

        # 6) Limity a výsledok
        lsl = self.lsl if self.lsl is not None else float("-inf")
        usl = self.usl if self.usl is not None else float("+inf")
        ok = (lsl <= measured <= usl)

        details = {
            "roi_xywh": roi,
            "shape": p_global.get("shape"),
            "width": int(p_global.get("width", 3)),
            "canny_lo": canny_lo, "canny_hi": canny_hi,
            "band_px": int(stats["band_px"]),
            "edges_px": int(stats["edges_px"]),
            "gap_px": int(stats["gap_px"]),
            "coverage_pct": float(stats["coverage_pct"]),
            "metric": metric,
        }
        details["preproc_desc"] = pre_desc
        details["preproc_preview"] = pre_preview
        return ToolResult(ok=ok, measured=measured, lsl=self.lsl, usl=self.usl, details=details, overlay=stats["overlay"])

class EdgeTraceLineTool(_EdgeTraceBase):   # type = "_wip_edge_line"
    pass

class EdgeTraceCircleTool(_EdgeTraceBase): # type = "_wip_edge_circle"
    pass

class EdgeTraceCurveTool(_EdgeTraceBase):  # type = "_wip_edge_curve"
    pass
