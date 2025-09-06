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
                if op == "median":
                    k = int(step.get("k", 3));  k = k if k % 2 == 1 else k+1
                    tmp = cv.medianBlur(img, max(1,k))
                    img = blend(tmp)
                elif op == "gaussian":
                    k = int(step.get("k", 3));  k = k if k % 2 == 1 else k+1
                    tmp = cv.GaussianBlur(img, (max(1,k), max(1,k)), 0)
                    img = blend(tmp)
                elif op == "bilateral":
                    d = int(step.get("d", 5)); sc = float(step.get("sigmaColor", 75.0)); ss = float(step.get("sigmaSpace", 75.0))
                    tmp = cv.bilateralFilter(img, max(1,d), sc, ss)
                    img = blend(tmp)
                elif op == "clahe":
                    clip = float(step.get("clip", 2.0)); tile = int(step.get("tile", 8))
                    clahe = cv.createCLAHE(clipLimit=max(0.1,clip), tileGridSize=(max(1,tile), max(1,tile)))
                    tmp = clahe.apply(img)
                    img = blend(tmp)
                elif op == "tophat":
                    k = int(step.get("k", 15));  k = k if k % 2 == 1 else k+1
                    se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k,k))
                    tmp = cv.morphologyEx(img, cv.MORPH_TOPHAT, se)
                    img = blend(tmp)
                elif op == "blackhat":
                    k = int(step.get("k", 15));  k = k if k % 2 == 1 else k+1
                    se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k,k))
                    tmp = cv.morphologyEx(img, cv.MORPH_BLACKHAT, se)
                    img = blend(tmp)
                elif op == "unsharp":
                    amt = float(step.get("amount", 1.0)); rad = int(step.get("radius", 3)); rad = rad if rad % 2 == 1 else rad+1
                    blur = cv.GaussianBlur(img, (max(1,rad), max(1,rad)), 0)
                    tmp = cv.addWeighted(img, 1.0 + amt, blur, -amt, 0)
                    img = blend(tmp)
                elif op == "normalize":
                    a = float(step.get("alpha", 0.0)); b = float(step.get("beta", 255.0))
                    tmp = cv.normalize(img, None, alpha=a, beta=b, norm_type=cv.NORM_MINMAX)
                    img = blend(tmp)
                else:
                    # neznámy op = preskoč
                    pass
            except Exception:
                # robustnosť: ak sa niečo pokazí, ideme ďalej s pôvodným img
                continue

        return img
