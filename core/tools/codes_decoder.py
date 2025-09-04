# core/tools/codes_decoder.py
from __future__ import annotations
from typing import List, Tuple, Optional, Dict, Any
import numpy as np
import cv2 as cv

try:
    from pylibdmtx.pylibdmtx import decode as dmtx_decode
except Exception:
    dmtx_decode = None

def _crop_roi(img: np.ndarray, roi: Optional[Tuple[int,int,int,int]]) -> np.ndarray:
    if roi is None: return img
    x,y,w,h = roi
    H,W = img.shape[:2]
    x1=max(0,x); y1=max(0,y); x2=min(W,x+w); y2=min(H,y+h)
    if x2<=x1 or y2<=y1: return img[0:0,0:0]
    return img[y1:y2,x1:x2]

def decode_codes(img: np.ndarray, roi: Optional[Tuple[int,int,int,int]] = None) -> List[Dict[str,Any]]:
    """
    ELI5: skúsi DataMatrix (pylibdmtx), potom QR (OpenCV). Vráti zoznam nálezov.
    """
    if img is None or img.size==0:
        return []
    roi_img = _crop_roi(img, roi)
    if roi_img.ndim==3:
        gray = cv.cvtColor(roi_img, cv.COLOR_BGR2GRAY)
    else:
        gray = roi_img

    results: List[Dict[str,Any]] = []

    # 1) DataMatrix (ak knižnica je)
    if dmtx_decode is not None:
        try:
            dec = dmtx_decode(gray)
            for d in dec:
                text = d.data.decode("utf-8", errors="ignore")
                results.append({"type":"dm","text":text})
        except Exception:
            pass

    # 2) QR (OpenCV)
    try:
        qr = cv.QRCodeDetector()
        ok, texts, pts = qr.detectAndDecodeMulti(gray)
        if ok and texts is not None:
            for t in texts:
                if t:
                    results.append({"type":"qr","text":t})
        else:
            t, pts = qr.detectAndDecode(gray)
            if t:
                results.append({"type":"qr","text":t})
    except Exception:
        pass

    return results
