# storage/dataset_store.py
from pathlib import Path
import time, cv2 as cv
import numpy as np

def _ts(): return time.strftime("%Y%m%d-%H%M%S")

def ensure_recipe_dirs(recipe: str):
    root = Path("datasets")/recipe
    (root/"ok").mkdir(parents=True, exist_ok=True)
    (root/"nok").mkdir(parents=True, exist_ok=True)
    return root

def save_ok(recipe: str, img: np.ndarray) -> str:
    root = ensure_recipe_dirs(recipe)
    p = root/"ok"/f"ok_{_ts()}.png"
    cv.imwrite(str(p), img)
    return str(p)

def save_nok(recipe: str, img: np.ndarray) -> str:
    root = ensure_recipe_dirs(recipe)
    p = root/"nok"/f"nok_{_ts()}.png"
    cv.imwrite(str(p), img)
    return str(p)
