# app/dev_codes_cli.py
import cv2 as cv
from core.tools.codes_decoder import decode_codes

img = cv.imread("samples/cur.png")
if img is None:
    raise FileNotFoundError("samples/cur.png")
# testujeme celú plochu (ROI=None)
codes = decode_codes(img, None)
print("Decoded:", codes)
