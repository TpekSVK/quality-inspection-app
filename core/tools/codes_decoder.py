# core/tools/codes_decoder.py
import cv2 as cv
import numpy as np
from typing import List, Tuple, Optional

try:
    from pylibdmtx.pylibdmtx import decode as dmtx_decode
except Exception:
    dmtx_decode = None

def crop_roi(img: np.ndarray, roi_xywh: Optional[Tuple[int,int,int,int]]) -> np.ndarray:
    if roi_xywh is None:
        return img
    x,y,w,h = roi_xywh
    x,y = max(0,x), max(0,y)
    return img[y:y+h, x:x+w].copy()

def decode_qr(img_bgr: np.ndarray) -> List[str]:
    """OpenCV QRCodeDetector (spoľahlivé, bez externých knižníc)."""
    det = cv.QRCodeDetector()
    data, points, _ = det.detectAndDecodeMulti(img_bgr)
    if isinstance(data, list):
        return [s for s in data if s]
    elif isinstance(data, str) and data:
        return [data]
    return []

def decode_dm(img_bgr: np.ndarray) -> List[str]:
    """Data Matrix – ak je dostupný pylibdmtx, inak prázdny zoznam."""
    if dmtx_decode is None:
        return []
    gray = cv.cvtColor(img_bgr, cv.COLOR_BGR2GRAY)
    res = dmtx_decode(gray)
    out = []
    for r in res:
        try:
            s = r.data.decode("utf-8", errors="ignore")
            if s: out.append(s)
        except: pass
    return out

def decode_codes(img_bgr: np.ndarray, roi_xywh: Optional[Tuple[int,int,int,int]]=None) -> List[str]:
    """
    ELI5: z obrázka/ROI načítame QR a prípadne DM.
    Vrátime list textov. Pre mapovanie do receptov pridáme prefix 'QR:' alebo 'DM:'.
    """
    roi = crop_roi(img_bgr, roi_xywh)
    if roi.ndim == 2:
        roi = cv.cvtColor(roi, cv.COLOR_GRAY2BGR)

    res_qr = decode_qr(roi)
    res_qr = [f"QR:{s}" for s in res_qr]
    res_dm = decode_dm(roi)
    res_dm = [f"DM:{s}" for s in res_dm]
    return res_qr + res_dm
