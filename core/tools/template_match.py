# core/tools/template_match.py
import cv2 as cv
import numpy as np
from .base_tool import BaseTool, ToolResult

def _apply_mask_intersection(x, y, w, h, mask_rects, roi_shape):
    """Maska (255=analyzuj, 0=ignoruj) v ROI-lokálnych súradniciach – presný prienik s ROI."""
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
    """Ľahký preproc – podobná logika ako v Builder preview (subset bežných operácií)."""
    if not chain:
        return gray_roi
    img = gray_roi.copy()
    def blend(tmp):
        if mask is None: return tmp
        return np.where(mask > 0, tmp, img)
    for st in chain:
        try:
            op = str(st.get("op","")).lower()
            if op == "median":
                k = int(st.get("k",3)); k = k if k % 2 == 1 else k + 1
                img = blend(cv.medianBlur(img, max(1, k)))
            elif op == "gaussian":
                k = int(st.get("k",3)); k = k if k % 2 == 1 else k + 1
                img = blend(cv.GaussianBlur(img, (max(1, k), max(1, k)), 0))
            elif op == "clahe":
                clip = float(st.get("clip", 2.0)); tile = int(st.get("tile", 8))
                clahe = cv.createCLAHE(clipLimit=max(0.1, clip), tileGridSize=(max(1, tile), max(1, tile)))
                img = blend(clahe.apply(img))
            elif op == "normalize":
                a = float(st.get("alpha", 0.0)); b = float(st.get("beta", 255.0))
                img = blend(cv.normalize(img, None, alpha=a, beta=b, norm_type=cv.NORM_MINMAX))
            elif op == "tophat":
                k = int(st.get("k",15)); k = k if k % 2 == 1 else k + 1
                se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k, k))
                img = blend(cv.morphologyEx(img, cv.MORPH_TOPHAT, se))
            elif op == "blackhat":
                k = int(st.get("k",15)); k = k if k % 2 == 1 else k + 1
                se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k, k))
                img = blend(cv.morphologyEx(img, cv.MORPH_BLACKHAT, se))
            elif op == "equalize":
                img = blend(cv.equalizeHist(img))
        except Exception:
            continue
    return img

class TemplateMatchTool(BaseTool):
    """
    Template Match (NCC):
      - Template = referenčný výrez v ROI (po prípadnom preproc).
      - Hľadáme v ROI na aktuálnom zábere, metóda cv.TM_CCOEFF_NORMED.
      Parametre:
        - min_score:   0..1 (default 0.7)
        - max_matches: max počet nálezov (default 5)
        - min_distance: NMS vzdialenosť (px) medzi nálezmi (default 12)
        - mode: "best" | "count"  (meraná hodnota = najlepšie skóre alebo počet nálezov)
        - preproc: []  (reťazec operácií)
        - mask_rects: []
    Výstup:
      - measured: best_score alebo count (podľa mode)
      - overlay:  ROI s nálezmi + skóre
      - details:  roi_xywh, mask_rects, preproc_desc, preproc_preview, ...
    """
    def run(self, img_ref, img_cur, fixture_transform=None):
        x, y, w, h = [int(v) for v in self.roi_xywh]
        Hc, Wc = img_cur.shape[:2]
        # bezpečné orezy
        x = max(0, min(x, Wc - 1)); y = max(0, min(y, Hc - 1))
        w = max(1, min(w, Wc - x));  h = max(1, min(h, Hc - y))

        p = dict(self.params or {})
        min_score   = float(p.get("min_score", 0.70))
        max_matches = int(p.get("max_matches", 5))
        min_dist    = int(p.get("min_distance", 12))
        mode        = str(p.get("mode", "best")).lower()
        chain       = p.get("preproc", []) or []
        mask_rects  = p.get("mask_rects", []) or []

        # ROI
        roi_ref = img_ref[y:y+h, x:x+w]
        roi_cur = img_cur[y:y+h, x:x+w]

        # maska prienikom
        m = _apply_mask_intersection(x, y, w, h, mask_rects, roi_ref.shape)

        # preproc (na oba, aby boli porovnateľné)
        roi_ref_p = _apply_preproc_chain(roi_ref, chain, mask=m)
        roi_cur_p = _apply_preproc_chain(roi_cur, chain, mask=m)

        # template = celá ROI z referencie (po preproc)
        tpl = roi_ref_p.copy()
        hh, ww = tpl.shape[:2]
        if hh < 3 or ww < 3:
            overlay = cv.cvtColor(roi_cur_p, cv.COLOR_GRAY2BGR)
            details = {
                "roi_xywh": [x, y, w, h],
                "mask_rects": mask_rects,
                "preproc_desc": self._preproc_desc(chain),
                "preproc_preview": roi_cur_p.copy()
            }
            # OK/NOK lokálne (bez _pass)
            measured = 0.0
            lsl, usl = self.lsl, self.usl
            ok = True
            if lsl is not None and measured < float(lsl): ok = False
            if usl is not None and measured > float(usl): ok = False
            return ToolResult(ok=ok, measured=0.0,
                            lsl=self.lsl, usl=self.usl,
                            details=details, overlay=overlay)



        # NCC mapa
        res = cv.matchTemplate(roi_cur_p, tpl, cv.TM_CCOEFF_NORMED)

        # maxima nad min_score + NMS podľa eukl. vzdialenosti
        loc = np.where(res >= min_score)
        pts = list(zip(loc[1].tolist(), loc[0].tolist()))  # (x,y) v ROI
        scores = [float(res[pt[1], pt[0]]) for pt in pts]

        order = np.argsort(scores)[::-1].tolist()
        kept = []
        for idx in order:
            px, py = pts[idx]; sc = scores[idx]
            # NMS
            ok_keep = True
            for (kx, ky, ks) in kept:
                if (px - kx)**2 + (py - ky)**2 < (min_dist**2):
                    ok_keep = False; break
            if ok_keep:
                kept.append((px, py, sc))
            if len(kept) >= max_matches:
                break

        # overlay do ROI
        overlay = cv.cvtColor(roi_cur_p, cv.COLOR_GRAY2BGR)
        for (px, py, sc) in kept:
            cv.rectangle(overlay, (px, py), (px + ww, py + hh), (0, 200, 0), 2, cv.LINE_AA)
            cv.putText(overlay, f"{sc:.2f}", (px, max(12, py - 4)),
                       cv.FONT_HERSHEY_SIMPLEX, 0.4, (0, 200, 0), 1, cv.LINE_AA)

        # metrika
        best = max([k[2] for k in kept], default=float(res.max()) if res.size else 0.0)
        count = len(kept)
        measured = float(count) if (mode == "count") else float(best)

        # OK/NOK lokálne (bez _pass)
        lsl, usl = self.lsl, self.usl
        ok_flag = True
        if lsl is not None and measured < float(lsl): ok_flag = False
        if usl is not None and measured > float(usl): ok_flag = False

        details = {
            "roi_xywh": [x, y, w, h],
            "mask_rects": mask_rects,
            "preproc_desc": self._preproc_desc(chain),
            "preproc_preview": roi_cur_p.copy(),
            "mode": mode,
            "min_score": min_score,
            "max_matches": max_matches,
            "min_distance": min_dist,
            "count": count,
            "best_score": best
        }
        return ToolResult(ok=ok_flag, measured=measured,
                        lsl=self.lsl, usl=self.usl,
                        details=details, overlay=overlay)




