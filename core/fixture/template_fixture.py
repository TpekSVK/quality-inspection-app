# core/fixture/template_fixture.py
import cv2 as cv
import numpy as np
from typing import Optional, Tuple

class TemplateFixture:
    """
    ELI5: V Teach si uložíme malý výrez (template) z referenčnej fotky.
    V Run tento template hľadáme v aktuálnej fotke => dostaneme posun (dx, dy).
    Rotáciu a scale v tejto jednoduchej verzii neriešime (v 1. kole netreba).
    Výsledok vrátime ako homogénnu maticu H (3x3), ktorou vie pipeline posunúť ROI.
    """

    def __init__(self, template_img: np.ndarray, method: int = cv.TM_CCOEFF_NORMED, min_score: float = 0.6):
        if template_img.ndim == 3:
            template_img = cv.cvtColor(template_img, cv.COLOR_BGR2GRAY)
        self.template = template_img
        self.h_t, self.w_t = template_img.shape[:2]
        self.method = method
        self.min_score = min_score

    def estimate_transform(self, img_cur: np.ndarray) -> Optional[np.ndarray]:
        if img_cur.ndim == 3:
            img_gray = cv.cvtColor(img_cur, cv.COLOR_BGR2GRAY)
        else:
            img_gray = img_cur

        res = cv.matchTemplate(img_gray, self.template, self.method)
        min_val, max_val, min_loc, max_loc = cv.minMaxLoc(res)

        if self.method in [cv.TM_SQDIFF, cv.TM_SQDIFF_NORMED]:
            score = 1.0 - min_val
            top_left = min_loc
        else:
            score = max_val
            top_left = max_loc

        if score < self.min_score:
            # nenašlo sa dosť dobre
            return None

        dx, dy = top_left[0], top_left[1]
        # homogénna matica posunu
        H = np.array([[1.0, 0.0, dx],
                      [0.0, 1.0, dy],
                      [0.0, 0.0, 1.0]], dtype=np.float32)
        return H
