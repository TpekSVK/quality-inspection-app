# core/tools/edge_trace.py
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import cv2 as cv

from .base_tool import BaseTool, ToolResult

# --- helpers ---

def _warp_to_ref(img: np.ndarray, ref_shape: Tuple[int,int], H: Optional[np.ndarray]) -> np.ndarray:
    """Zarovná aktuálny obraz na rozmer referencie (h,w)."""
    h_ref, w_ref = ref_shape
    if H is not None:
        return cv.warpPerspective(img, H, (w_ref, h_ref))
    # bez fixtúry – ak rozmer nesedí, doriešime resize (rovnako to robí RUN overlay)
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
    """Prekonvertuje globálne súradnice kresby do lokálnych (v rámci ROI)."""
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
    """Binárna maska 'pásu' okolo lokálneho tvaru v ROI (255=kontroluj)."""
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

def _edge_density_gaps(img_gray: np.ndarray, band_mask: np.ndarray,
                       canny_lo: int, canny_hi: int) -> Dict[str, Any]:
    """Canny hrany → koľko px v páse NEMÁ hranu (gap)."""
    edges = cv.Canny(img_gray, canny_lo, canny_hi)
    band = (band_mask > 0)
    band_px = int(band.sum())
    edges_px = int((edges > 0)[band].sum())
    gap_px = max(0, band_px - edges_px)

    # overlay (BGR): červený pás, zelené pixely tam, kde sú hrany v páse
    overlay = cv.cvtColor(img_gray, cv.COLOR_GRAY2BGR)
    overlay[band] = (0, 0, 255)      # pás
    green = (edges > 0) & band
    overlay[green] = (0, 255, 0)     # hrany v páse

    return {"gap_px": gap_px, "band_px": band_px, "edges_px": edges_px, "overlay": overlay}

# --- tooly ---

class _EdgeTraceBase(BaseTool):
    """
    ELI5: Najprv aktuálny záber zarovnáme na referenciu (fixtúra),
    potom v ROI pozrieme „pás“ okolo tvojej čiary/kruhu/krivky.
    Measured = počet px v páse bez hrán (gap_px) → čím menej, tým lepšie.
    """
    def run(self, img_ref: np.ndarray, img_cur: np.ndarray, fixture_transform: Optional[np.ndarray]) -> ToolResult:
        # 0) bezpečnosť
        if img_ref is None or img_cur is None or img_cur.size == 0:
            return ToolResult(False, 0.0, self.lsl, self.usl, {"error":"empty image", "roi_xywh": self.roi_xywh})

        # 1) ZAROVNAJ na referenciu (ako ostatné tooly), aby súradnice sedeli
        ref_shape = img_ref.shape[:2]   # (h,w)
        cur_ref = _warp_to_ref(img_cur, ref_shape, fixture_transform)  # zarovnaný na rozmer ref
        if cur_ref.ndim == 3: cur_gray = cv.cvtColor(cur_ref, cv.COLOR_BGR2GRAY)
        else: cur_gray = cur_ref

        # 2) Vystrihni ROI v referenčných súradniciach
        x, y, w, h = [int(v) for v in self.roi_xywh]
        roi = (x, y, w, h)
        roi_gray = _safe_crop(cur_gray, roi)
        if roi_gray.size == 0:
            return ToolResult(False, 0.0, self.lsl, self.usl, {"error":"roi out of bounds", "roi_xywh": roi})

        # 3) Prekonvertuj kresbu do LOKÁLNYCH súradníc ROI (odpočítame x,y)
        p_global = dict(self.params or {})
        p_local = _shape_to_roi_local(p_global, roi)

        # 4) Vytvor pás okolo kresby a spočítaj „gapy“ hrán
        band = _draw_shape_mask(roi_gray.shape[0], roi_gray.shape[1], p_local)
        if band.sum() == 0:
            return ToolResult(False, 0.0, self.lsl, self.usl, {"error":"shape mask empty (nakresli tvar)", "roi_xywh": roi})
        canny_lo = int(p_global.get("canny_lo", 40))
        canny_hi = int(p_global.get("canny_hi", 120))
        met = _edge_density_gaps(roi_gray, band, canny_lo, canny_hi)
        measured = float(met["gap_px"])

        # 5) Limitovanie + detaily pre RUN overlay
        lsl = self.lsl if self.lsl is not None else float("-inf")
        usl = self.usl if self.usl is not None else float("+inf")
        ok = (lsl <= measured <= usl)

        details = {
            "roi_xywh": roi,
            "shape": p_global.get("shape"),
            "width": int(p_global.get("width", 3)),
            "canny_lo": canny_lo, "canny_hi": canny_hi,
            "gap_px": int(met["gap_px"]), "band_px": int(met["band_px"]), "edges_px": int(met["edges_px"]),
        }
        return ToolResult(ok=ok, measured=measured, lsl=self.lsl, usl=self.usl, details=details, overlay=met["overlay"])

class EdgeTraceLineTool(_EdgeTraceBase):   # type = "_wip_edge_line"
    pass

class EdgeTraceCircleTool(_EdgeTraceBase): # type = "_wip_edge_circle"
    pass

class EdgeTraceCurveTool(_EdgeTraceBase):  # type = "_wip_edge_curve"
    pass
