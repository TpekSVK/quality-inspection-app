# ui_style.py

# ---------- Vizuálne konštanty pre kreslenie (Builder aj RUN) ----------

# RGB (Qt/QPainter používa RGB)
ROI_RGB    = (33, 150, 243)   # modrá (ROI)
MASK_RGB   = (156, 39, 176)   # fialová (masky)
SHAPE_RGB  = (255, 193, 7)    # žltá (linky/krivky/kruhy v Builderi)
DETECT_RGB = (0, 200, 0)      # zelená (detekcie/nálezy)

# BGR (OpenCV používa BGR)
def _rgb2bgr(c): return (c[2], c[1], c[0])
ROI_BGR    = _rgb2bgr(ROI_RGB)
MASK_BGR   = _rgb2bgr(MASK_RGB)
SHAPE_BGR  = _rgb2bgr(SHAPE_RGB)
DETECT_BGR = _rgb2bgr(DETECT_RGB)

# Hrúbky čiar (px)
PEN_THIN  = 2
PEN_THICK = 3

# ---------- Tvoje existujúce štýly tlačidiel ----------
TOOLBUTTON = """
QToolButton {
  background: #2b2b2b;
  color: #ffffff;
  border: 1px solid #3a3a3a;
  border-radius: 8px;
  padding: 6px 10px;
}
QToolButton:hover { background: #333333; }
QToolButton:checked {
  background: #4caf50;
  border-color: #4caf50;
  color: #ffffff;
}
"""

PRIMARY_BUTTON = """
QToolButton {
  background: #2962ff;
  color: #ffffff;
  border: 1px solid #1e40ff;
  border-radius: 8px;
  padding: 8px 14px;
}
QToolButton:hover { background: #1f54ff; }
QToolButton:disabled { background: #555; color: #bbb; border-color: #666; }
"""
