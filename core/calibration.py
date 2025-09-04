# core/calibration.py
from __future__ import annotations
from typing import Tuple, Dict
import math

def pxmm_from_two_points(pt1_px: Tuple[float,float], pt2_px: Tuple[float,float], distance_mm: float) -> Dict[str,float]:
    """
    ELI5: vyber na snímke dva body, ktoré v realite ležia 'distance_mm' od seba.
    Spočítam pixlovú vzdialenosť a z nej mm/px. Vráti sa izotropná kalibrácia (X=Y).
    """
    dx = float(pt2_px[0] - pt1_px[0])
    dy = float(pt2_px[1] - pt1_px[1])
    dpx = math.hypot(dx, dy)
    if dpx <= 0:
        raise ValueError("Body sa zhodujú – vzdialenosť v px je 0.")
    mm_per_px = float(distance_mm) / dpx
    return {"mm_per_px_x": mm_per_px, "mm_per_px_y": mm_per_px}

def px_per_mm_from_pxmm(pxmm: Dict[str,float]) -> Dict[str,float]:
    """Pomocná inverzia: px/mm z mm/px."""
    x = pxmm.get("mm_per_px_x", 0.0)
    y = pxmm.get("mm_per_px_y", 0.0)
    return {
        "px_per_mm_x": (1.0/x if x else 0.0),
        "px_per_mm_y": (1.0/y if y else 0.0),
    }
