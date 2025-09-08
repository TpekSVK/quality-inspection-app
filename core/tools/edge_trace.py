# core/tools/edge_trace.py
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import cv2 as cv
import math
from .base_tool import BaseTool, ToolResult

# --- helpers ---

def _safe_crop(img: np.ndarray, roi: Tuple[int,int,int,int]) -> np.ndarray:
    x, y, w, h = [int(v) for v in roi]
    H, W = img.shape[:2]
    x1 = max(0, x); y1 = max(0, y)
    x2 = min(W, x + w); y2 = min(H, y + h)
    if x2 <= x1 or y2 <= y1:
        return img[0:0, 0:0]
    return img[y1:y2, x1:x2]

def _shape_to_roi_local(params: Dict[str, Any], roi_xywh: Tuple[int,int,int,int]) -> Dict[str, Any]:
    """Prevedie globálne shape súradnice na ROI-lokálne."""
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
    """Vytvorí binárnu masku „pásu“ okolo shape (line/circle/polyline)."""
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
        pts = params_local.get("pts", []
)
        if len(pts) >= 2:
            arr = np.array([[int(x),int(y)] for (x,y) in pts], dtype=np.int32)
            cv.polylines(m, [arr], False, 255, thickness=width, lineType=cv.LINE_AA)
    return m

def _edge_stats(img_gray: np.ndarray, band_mask: np.ndarray,
                canny_lo: int, canny_hi: int) -> Dict[str, Any]:
    """Pôvodná plošná metrika – koľko Canny hrán leží v páse."""
    edges = cv.Canny(img_gray, canny_lo, canny_hi)
    band = (band_mask > 0)
    band_px = int(band.sum())
    edges_px = int((edges > 0)[band].sum())
    gap_px = max(0, band_px - edges_px)
    coverage_pct = (100.0 * edges_px / band_px) if band_px > 0 else 0.0

    overlay = cv.cvtColor(img_gray, cv.COLOR_GRAY2BGR)
    overlay[band] = (0, 0, 255)           # pás
    green = (edges > 0) & band
    overlay[green] = (0, 255, 0)           # nájdené hrany v páse

    return {
        "band_px": band_px,
        "edges_px": edges_px,
        "gap_px": gap_px,
        "coverage_pct": float(coverage_pct),
        "overlay": overlay,
    }

# --- nové: profil pozdĺž čiary + vzdialenosť hrán ---

def _rotate_image_keep_size(img: np.ndarray, center: Tuple[float,float], angle_deg: float) -> Tuple[np.ndarray, np.ndarray]:
    """Otočí obraz okolo stredu, vráti (rot_img, M) s transformačnou maticou."""
    M = cv.getRotationMatrix2D(center, angle_deg, 1.0)
    rot = cv.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv.INTER_LINEAR)
    return rot, M

def _affine_inv(M: np.ndarray) -> np.ndarray:
    A = M[:, :2]; b = M[:, 2:3]
    Ai = cv.invert(A)[1]
    Mi = np.zeros_like(M)
    Mi[:, :2] = Ai
    Mi[:, 2:3] = -Ai @ b
    return Mi

def _profile_along_line(roi_gray: np.ndarray, x1:int, y1:int, x2:int, y2:int, width:int) -> Dict[str, Any]:
    """Vyreže horizontálny pás pozdĺž čiary (po rotácii), spriemeruje do 1D profilu."""
    h, w = roi_gray.shape[:2]
    cx = (x1 + x2) * 0.5
    cy = (y1 + y2) * 0.5
    angle = -math.degrees(math.atan2(y2 - y1, x2 - x1))  # aby sa čiara stala horizontálna
    rot, M = _rotate_image_keep_size(roi_gray, (cx, cy), angle)

    # transformuj body do rot priestoru
    P = np.array([[x1, y1, 1.0], [x2, y2, 1.0]], dtype=np.float32).T  # 3x2
    Q = (M @ P).T  # 2 body po rotácii
    x1r, y1r = Q[0]; x2r, y2r = Q[1]
    y_line = int(round((y1r + y2r) * 0.5))
    x_start = int(round(min(x1r, x2r)))
    x_end   = int(round(max(x1r, x2r)))
    x_start = max(0, min(rot.shape[1]-1, x_start))
    x_end   = max(0, min(rot.shape[1]-1, x_end))
    if x_end <= x_start:
        return {"ok": False}

    # výška pásu
    half = max(1, int(round(width/2)))
    y0 = max(0, y_line - half)
    y1b = min(rot.shape[0], y_line + half + 1)
    strip = rot[y0:y1b, x_start:x_end]

    if strip.size == 0 or strip.shape[1] < 3:
        return {"ok": False}

    # jemné vyhladenie a priemer cez výšku -> 1D profil
    strip = cv.GaussianBlur(strip, (0,0), 1.0)
    prof = strip.mean(axis=0).astype(np.float32)  # shape [L]

    return {
        "ok": True,
        "profile": prof,                 # 1D intenzita
        "x_start": x_start,
        "y_line": y_line,
        "M": M,
        "rot_shape": rot.shape[:2],
    }

def _pick_edges_from_profile(prof: np.ndarray, polarity: str, grad_thresh: float) -> Dict[str, Any]:
    """Nájde hrany v 1D profile podľa polarity a prahu na deriváciu."""
    if prof is None or len(prof) < 3:
        return {"idx_all": []}
    g = np.diff(prof)  # gradient
    if polarity == "dark2light":
        score = g
    elif polarity == "light2dark":
        score = -g
    else:  # auto
        score = np.abs(g)

    # prah
    thr = float(grad_thresh)
    if thr <= 0:
        thr = float(np.percentile(np.abs(g), 75))  # adaptívny fallback
        thr = max(5.0, thr)

    idx = np.where(score >= thr)[0]  # index hrany ~ medzi i a i+1
    if idx.size == 0:
        return {"idx_all": []}

    # strongest = max(score)
    strongest = int(idx[np.argmax(score[idx])])
    return {
        "idx_all": idx.astype(int).tolist(),
        "first": int(idx.min()),
        "last": int(idx.max()),
        "strongest": strongest,
        "score": score,
    }

def _draw_edge_marks_on_overlay(overlay: np.ndarray, M: np.ndarray, x_start:int, y_line:int, idxs: List[int], color=(0,255,0)):
    """Vykreslí značky hrán (v pôvodnom – neroztočenom – ROI priestore)."""
    Mi = _affine_inv(M)
    for i in idxs:
        xr = x_start + int(i)
        pt_rot = np.array([ [xr, y_line, 1.0] ], dtype=np.float32).T  # 3x1
        pt = (Mi @ pt_rot).flatten()
        x, y = int(round(pt[0])), int(round(pt[1]))
        if 0 <= x < overlay.shape[1] and 0 <= y < overlay.shape[0]:
            cv.circle(overlay, (x,y), 3, color, -1, lineType=cv.LINE_AA)

# --- tools ---

class _EdgeTraceBase(BaseTool):
    def run(self, img_ref: np.ndarray, img_cur: np.ndarray, fixture_transform: Optional[np.ndarray]) -> ToolResult:
        if img_ref is None or img_cur is None or img_cur.size == 0:
            return ToolResult(False, 0.0, self.lsl, self.usl, {"error":"empty image", "roi_xywh": self.roi_xywh})

        # 1) Zarovnanie na referenciu (BaseTool)
        cur_ref = self.align_current_to_ref(img_ref, img_cur, fixture_transform)
        cur_gray = cv.cvtColor(cur_ref, cv.COLOR_BGR2GRAY) if cur_ref.ndim == 3 else cur_ref

        # 2) ROI crop
        x, y, w, h = [int(v) for v in self.roi_xywh]
        roi = (x, y, w, h)
        roi_gray = _safe_crop(cur_gray, roi)
        if roi_gray.size == 0:
            return ToolResult(False, 0.0, self.lsl, self.usl, {"error":"roi out of bounds", "roi_xywh": roi})

        # 3) Shape → ROI-lokálne
        p_global = dict(self.params or {})
        p_local = _shape_to_roi_local(p_global, roi)

        band = _draw_shape_mask(roi_gray.shape[0], roi_gray.shape[1], p_local)
        if band.sum() == 0:
            return ToolResult(False, 0.0, self.lsl, self.usl, {"error":"shape mask empty (nakresli tvar)", "roi_xywh": roi})

        # 4) Predspracovanie v ROI (rešpektuje masky)
        pre_desc = "—"
        pre_preview = None
        mask_rects = (self.params or {}).get("mask_rects", []) or []
        full_mask = self.roi_mask_intersection(x, y, w, h, mask_rects, roi_shape=roi_gray.shape) if mask_rects else None

        chain = p_global.get("preproc", []) or []
        if chain:
            roi_gray = self._apply_preproc_chain(roi_gray, chain, mask=full_mask)
            pre_desc = self._preproc_desc(chain)
            pre_preview = cv.cvtColor(roi_gray, cv.COLOR_GRAY2BGR)

        # 5) Parametre a metrika
        canny_lo = int(p_global.get("canny_lo", 40))
        canny_hi = int(p_global.get("canny_hi", 120))
        metric = str(p_global.get("metric", "px_gap")).lower()

        # NOVÉ: pre „edge_distance“ používame profil pozdĺž LINE
        measured = None
        extra = {}
        overlay = None

        if p_local.get("shape") == "line" and len(p_local.get("pts", [])) == 2 and metric in ("edge_distance", "edge_pos"):
            (x1,y1),(x2,y2) = p_local["pts"]
            width = int(max(1, p_local.get("width", 3)))
            pol = str(p_global.get("polarity", "auto")).lower()   # auto | dark2light | light2dark
            grad_thr = float(p_global.get("grad_thresh", 0))      # 0 = adaptívny
            edge_pick = str(p_global.get("edge_pick", "strongest")).lower()  # first|last|strongest (pre edge_pos)

            prof = _profile_along_line(roi_gray, x1,y1,x2,y2, width)
            if not prof.get("ok"):
                return ToolResult(False, 0.0, self.lsl, self.usl, {"error":"profile failed", "roi_xywh": roi})

            picks = _pick_edges_from_profile(prof["profile"], pol, grad_thr)
            idx_all = picks.get("idx_all", [])

            if metric == "edge_distance":
                if len(idx_all) >= 2:
                    a = picks.get("first")
                    b = picks.get("last")
                    measured = float(abs(b - a))
                else:
                    measured = 0.0
            else:  # edge_pos
                if len(idx_all) >= 1:
                    sel = picks.get({"first":"first","last":"last"}.get(edge_pick, "strongest"))
                    measured = float(int(sel))
                else:
                    measured = -1.0  # nič nenašlo – voliteľne si dáš LSL/USL mimo

            # overlay: pás + hrany (zelené body)
            overlay = cv.cvtColor(roi_gray, cv.COLOR_GRAY2BGR)
            overlay[band > 0] = (0,0,255)  # pás
            _draw_edge_marks_on_overlay(overlay, prof["M"], prof["x_start"], prof["y_line"], idx_all, color=(0,255,0))

            extra.update({
                "edge_first": picks.get("first", -1),
                "edge_last":  picks.get("last", -1),
                "edge_strongest": picks.get("strongest", -1),
                "polarity": pol,
                "grad_thresh": float(grad_thr),
                "edge_pick": edge_pick,
            })

        else:
            # Pôvodné metriky cez Canny v páse
            stats = _edge_stats(roi_gray, band, canny_lo, canny_hi)
            if metric == "coverage_pct":
                measured = float(stats["coverage_pct"])
                overlay = stats["overlay"]
            else:
                metric = "px_gap"
                measured = float(stats["gap_px"])
                overlay = stats["overlay"]
            extra.update({
                "band_px": int(stats["band_px"]),
                "edges_px": int(stats["edges_px"]),
                "gap_px": int(stats["gap_px"]),
                "coverage_pct": float(stats["coverage_pct"]),
            })


        # 6) Limity a výsledok
        lsl = self.lsl if self.lsl is not None else float("-inf")
        usl = self.usl if self.usl is not None else float("+inf")
        ok = (lsl <= measured <= usl)

        details = {
            "roi_xywh": roi,
            "mask_rects": mask_rects,
            "shape": p_global.get("shape"),
            "width": int(p_global.get("width", 3)),
            "canny_lo": canny_lo, "canny_hi": canny_hi,
            "metric": metric,
        }
        details.update(extra)
        details["preproc_desc"] = pre_desc
        details["preproc_preview"] = pre_preview

        return ToolResult(ok=ok, measured=float(measured), lsl=self.lsl, usl=self.usl, details=details, overlay=overlay)

class EdgeTraceLineTool(_EdgeTraceBase):   # type = "edge_line"
    pass

class EdgeTraceCircleTool(_EdgeTraceBase): # type = "edge_circle"
    pass

class EdgeTraceCurveTool(_EdgeTraceBase):  # type = "edge_curve"
    pass
