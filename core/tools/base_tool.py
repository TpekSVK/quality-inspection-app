from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Tuple, Optional, List
import numpy as np
import cv2 as cv

@dataclass
class ToolResult:
    ok: bool
    measured: float
    lsl: Optional[float]
    usl: Optional[float]
    details: Dict[str, Any]   # napr. plocha_blobov, count, bboxy
    overlay: Optional[np.ndarray] = None  # voliteľná grafika do overlay

class BaseTool(ABC):
    """Všetky tools majú jednotné API a per-ROI nastavenia."""
    def __init__(self, name: str, roi_xywh: Tuple[int,int,int,int], params: Dict[str, Any], lsl=None, usl=None, units: str="px"):
        self.name = name
        self.roi_xywh = roi_xywh
        self.params = params or {}
        self.lsl = lsl
        self.usl = usl
        self.units = units

    @abstractmethod
    def run(self, img_ref: np.ndarray, img_cur: np.ndarray, fixture_transform: Optional[np.ndarray]) -> ToolResult:
        """
        img_ref: referenčná fotka (Teach)
        img_cur: aktuálny snímok (Run)
        fixture_transform: 3x3 homogénna matica (alebo None)
        """
        ...

    # -------------------- PRE-PROC HELPER (aplikuje sa len v ROI) --------------------

    def _apply_preproc_chain(self, roi_gray: np.ndarray, chain: Optional[List[Dict[str, Any]]], mask: Optional[np.ndarray]=None) -> np.ndarray:
        """
        ELI5: vezmeme ROI (šedý obraz) a postupne cez 'chain' preženieme filtre.
        Ak je 'mask' (255=analyzuj, 0=ignoruj), filter sa aplikuje len tam,
        inde necháme pôvodné pixely (bez artefaktov na hranách).
        chain = [{"op":"median","k":3}, {"op":"clahe","clip":2.0,"tile":8}, ...]
        """
        if roi_gray is None or roi_gray.size == 0:
            return roi_gray
        if not chain:
            return roi_gray

        img = roi_gray.copy()
        m = mask
        if m is not None:
            if m.ndim == 3:
                m = cv.cvtColor(m, cv.COLOR_BGR2GRAY)
            _, m = cv.threshold(m, 1, 255, cv.THRESH_BINARY)

        def blend(tmp: np.ndarray) -> np.ndarray:
            if m is None:
                return tmp
            # len kde m>0 nahradíme filtrovaným, inde necháme pôvodný
            return np.where(m[..., None] > 0, tmp if tmp.ndim == 3 else tmp[..., None], img if img.ndim == 3 else img[..., None]).squeeze()

        for step in chain:
            try:
                op = str(step.get("op","")).lower().strip()

                # --- existujúce op ---
                if op == "median":
                    k = int(step.get("k", 3));  k = k if k % 2 == 1 else k+1
                    tmp = cv.medianBlur(img, max(1,k));  img = blend(tmp)

                elif op == "gaussian":
                    k = int(step.get("k", 3));  k = k if k % 2 == 1 else k+1
                    tmp = cv.GaussianBlur(img, (max(1,k), max(1,k)), 0);  img = blend(tmp)

                elif op == "bilateral":
                    d = int(step.get("d", 5)); sc = float(step.get("sigmaColor", 75.0)); ss = float(step.get("sigmaSpace", 75.0))
                    tmp = cv.bilateralFilter(img, max(1,d), sc, ss);  img = blend(tmp)

                elif op == "clahe":
                    clip = float(step.get("clip", 2.0)); tile = int(step.get("tile", 8))
                    clahe = cv.createCLAHE(clipLimit=max(0.1,clip), tileGridSize=(max(1,tile), max(1,tile)))
                    tmp = clahe.apply(img);  img = blend(tmp)

                elif op == "tophat":
                    k = int(step.get("k", 15));  k = k if k % 2 == 1 else k+1
                    se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k,k))
                    tmp = cv.morphologyEx(img, cv.MORPH_TOPHAT, se);  img = blend(tmp)

                elif op == "blackhat":
                    k = int(step.get("k", 15));  k = k if k % 2 == 1 else k+1
                    se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k,k))
                    tmp = cv.morphologyEx(img, cv.MORPH_BLACKHAT, se);  img = blend(tmp)

                elif op == "unsharp":
                    amt = float(step.get("amount", 1.0)); rad = int(step.get("radius", 3)); rad = rad if rad % 2 == 1 else rad+1
                    blur = cv.GaussianBlur(img, (max(1,rad), max(1,rad)), 0)
                    tmp = cv.addWeighted(img, 1.0 + amt, blur, -amt, 0);  img = blend(tmp)

                elif op == "normalize":
                    a = float(step.get("alpha", 0.0)); b = float(step.get("beta", 255.0))
                    tmp = cv.normalize(img, None, alpha=a, beta=b, norm_type=cv.NORM_MINMAX);  img = blend(tmp)

                # --- nové op ---
                elif op == "morphgrad":
                    k = int(step.get("k", 3));  k = k if k % 2 == 1 else k+1
                    se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k,k))
                    dil = cv.dilate(img, se);  ero = cv.erode(img, se)
                    tmp = cv.subtract(dil, ero);  img = blend(tmp)

                elif op == "log":  # Laplacian of Gaussian
                    k = int(step.get("k", 5));  k = k if k % 2 == 1 else k+1
                    blur = cv.GaussianBlur(img, (k,k), 0)
                    lap  = cv.Laplacian(blur, cv.CV_16S, ksize=3)
                    tmp  = cv.convertScaleAbs(lap)
                    img = blend(tmp)

                elif op == "homo":  # jednoduchý „homomorphic/SSR“: log(I) - log(blur(I))
                    sigma = float(step.get("sigma", 30.0))
                    gain  = float(step.get("gain", 1.0))
                    f = img.astype(np.float32) + 1.0
                    L = cv.GaussianBlur(f, (0,0), sigmaX=max(0.1, sigma))
                    res = (np.log(f) - np.log(L)) * gain
                    res = cv.normalize(res, None, 0, 255, cv.NORM_MINMAX).astype(np.uint8)
                    img = blend(res)

                elif op == "retinex":  # SSR
                    sigma = float(step.get("sigma", 30.0))
                    f = img.astype(np.float32) + 1.0
                    L = cv.GaussianBlur(f, (0,0), sigmaX=max(0.1, sigma))
                    res = np.log(f) - np.log(L)
                    res = cv.normalize(res, None, 0, 255, cv.NORM_MINMAX).astype(np.uint8)
                    img = blend(res)

                elif op == "guided":
                    r = int(step.get("r", 5)); eps = float(step.get("eps", 1e-3))
                    try:
                        # vyžaduje cv.ximgproc (ak chýba, fallback)
                        gf = cv.ximgproc.guidedFilter(img, img, r, eps)
                        tmp = np.clip(gf, 0, 255).astype(np.uint8)
                    except Exception:
                        tmp = cv.bilateralFilter(img, d=max(1, r*2+1), sigmaColor=40, sigmaSpace=40)
                    img = blend(tmp)

                elif op == "nlm":
                    h = float(step.get("h", 10.0))
                    tmp = cv.fastNlMeansDenoising(img, None, h=h, templateWindowSize=7, searchWindowSize=21)
                    img = blend(tmp)

                elif op == "rollball":  # morfologické open = odhad pozadia, potom odpočítať
                    r = int(step.get("r", 25)); r = r if r % 2 == 1 else r+1
                    se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (r,r))
                    bg = cv.morphologyEx(img, cv.MORPH_OPEN, se)
                    tmp = cv.subtract(img, bg)
                    img = blend(tmp)

                elif op == "sauvola":  # binarizácia (môže ísť aj pred edge trace/diff)
                    win = int(step.get("win", 25));  win = win if win % 2 == 1 else win+1
                    k   = float(step.get("k", 0.2))
                    f = img.astype(np.float32)
                    mean = cv.boxFilter(f, ddepth=-1, ksize=(win, win), normalize=True)
                    mean2 = cv.boxFilter(f*f, ddepth=-1, ksize=(win, win), normalize=True)
                    var = np.clip(mean2 - mean*mean, 0, None)
                    std = np.sqrt(var)
                    R = 128.0
                    th = mean * (1.0 + k*((std / R) - 1.0))
                    tmp = (f > th).astype(np.uint8) * 255
                    img = blend(tmp)

                elif op == "zscore":
                    f = img.astype(np.float32)
                    mu = float(f.mean()); sd = float(f.std()) if f.std()>1e-6 else 1.0
                    z = (f - mu) / sd
                    tmp = cv.normalize(z, None, 0, 255, cv.NORM_MINMAX).astype(np.uint8)
                    img = blend(tmp)

                elif op == "clip":  # percentilový orez + rescale
                    lo = float(step.get("lo", 5.0)); hi = float(step.get("hi", 95.0))
                    lo = max(0.0, min(100.0, lo)); hi = max(lo+0.1, min(100.0, hi))
                    p1, p2 = np.percentile(img, [lo, hi])
                    if p2 <= p1: p2 = p1 + 1.0
                    f = np.clip(img.astype(np.float32), p1, p2)
                    tmp = ((f - p1) * (255.0/(p2 - p1))).astype(np.uint8)
                    img = blend(tmp)

                elif op == "equalize":
                    tmp = cv.equalizeHist(img); img = blend(tmp)

                elif op == "gabor":
                    # angles: zoznam stupňov; freq: cykly/pixel -> lambda = 1/freq
                    angles = step.get("angles", [0,45,90,135])
                    freq   = float(step.get("freq", 0.15))
                    if freq <= 0: freq = 0.15
                    lmbd = 1.0/max(1e-6, freq)
                    ksize = int(step.get("ksize", 21)); ksize = ksize if ksize % 2 == 1 else ksize+1
                    sigma = float(step.get("sigma", ksize/6.0))
                    gamma = float(step.get("gamma", 0.5))
                    acc = None
                    for a in angles:
                        try:
                            theta = np.deg2rad(float(a))
                            kern = cv.getGaborKernel((ksize, ksize), sigma, theta, lmbd, gamma, 0, ktype=cv.CV_32F)
                            resp = cv.filter2D(img, cv.CV_32F, kern)
                            acc = resp if acc is None else np.maximum(acc, resp)
                        except Exception:
                            continue
                    if acc is not None:
                        tmp = cv.normalize(acc, None, 0, 255, cv.NORM_MINMAX).astype(np.uint8)
                        img = blend(tmp)

                else:
                    # neznámy op = preskoč
                    pass

            except Exception:
                # robustnosť: ak sa niečo pokazí, ideme ďalej s pôvodným img
                continue

        return img

    def _preproc_desc(self, chain: Optional[List[Dict[str, Any]]]) -> str:
        if not chain:
            return "—"
        parts=[]
        for st in chain:
            op = st.get("op","?")
            p  = ", ".join([f"{k}={v}" for k,v in st.items() if k!="op"])
            parts.append(f"{op}({p})" if p else op)
        return " → ".join(parts)
    # v class BaseTool:
    @staticmethod
    def roi_mask_intersection(x, y, w, h, mask_rects, roi_shape):
        """ROI-lokálna maska (255=analyzuj) ako prienik ROI a mask_rects."""
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

    @staticmethod
    def align_current_to_ref(img_ref, img_cur, fixture_transform=None):
        """Zarovná curr. frame na veľkosť/rovinu referencie (warp H alebo resize)."""
        if fixture_transform is not None:
            return cv.warpPerspective(img_cur, fixture_transform, (img_ref.shape[1], img_ref.shape[0]))
        if img_cur.shape[:2] != img_ref.shape[:2]:
            return cv.resize(img_cur, (img_ref.shape[1], img_ref.shape[0]), interpolation=cv.INTER_LINEAR)
        return img_cur
