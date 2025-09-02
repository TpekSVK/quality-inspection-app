# core/tools/anomaly_autoteach.py
import cv2 as cv
import numpy as np
from typing import List, Tuple, Optional, Dict, Any, Callable
from .base_tool import BaseTool
from .diff_from_ref import DiffFromRefTool
from .anomaly_utils import percentile_threshold

class AutoteachCalibrator:
    """
    ELI5: spustíme vybraný tool na množine OK snímok, pozbierame 'measured' a nastavíme prah (LSL/USL)
    podľa cieľového FPR.
    """

    def __init__(self, target_fpr: float = 0.003):
        self.target_fpr = target_fpr

    def calibrate_usl(self, tool: BaseTool,
                      ref_img: np.ndarray,
                      ok_imgs: List[np.ndarray],
                      fixture_transform: Optional[np.ndarray]) -> float:
        values: List[float] = []
        for im in ok_imgs:
            r = tool.run(ref_img, im, fixture_transform)
            values.append(float(r.measured))
        usl = percentile_threshold(values, self.target_fpr)
        return usl

    def apply_to_recipe_tool(self, recipe_tool: Dict[str, Any], new_usl: float) -> Dict[str, Any]:
        r = dict(recipe_tool)
        r["usl"] = float(new_usl)
        # voliteľne uložiť aj meta-info o kalibrácii
        meta = r.get("autoteach_meta", {})
        meta["target_fpr"] = self.target_fpr
        r["autoteach_meta"] = meta
        return r
