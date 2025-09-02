# scripts/make_synthetic_samples.py
import cv2 as cv
import numpy as np
from pathlib import Path

Path("samples").mkdir(exist_ok=True)

H, W = 960, 1280   # menšie pre rýchly test
ref = np.full((H, W), 140, np.uint8)            # uniformne šedé pozadie
cv.rectangle(ref, (200,150), (1080,800), 150, -1)  # veľká svetlejšia plocha (OK)
cv.circle(ref, (400,400), 60, 120, -1)             # tmavší kruh (OK feature)

cur = ref.copy()
# pridáme 3 „vady“ (bude ich vidieť v diffe)
cv.circle(cur, (600, 500), 15, 255, -1)  # biely bod
cv.circle(cur, (700, 600), 12, 60, -1)   # tmavý bod
cv.rectangle(cur, (900, 300), (940, 340), 30, -1)  # malý tmavý štvorec

cv.imwrite("samples/ref.png", ref)
cv.imwrite("samples/cur.png", cur)
print("OK -> samples/ref.png + samples/cur.png")
