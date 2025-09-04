# app/widgets/roi_drawer.py
from PyQt5 import QtWidgets, QtGui, QtCore
import numpy as np

COLOR_ROI = QtGui.QColor(33, 150, 243)     # modrá
COLOR_MASK = QtGui.QColor(156, 39, 176)    # fialová

class ROIDrawer(QtWidgets.QLabel):
    roiChanged = QtCore.pyqtSignal(int, int, int, int)     # x,y,w,h
    maskAdded = QtCore.pyqtSignal(int, int, int, int)      # x,y,w,h
    masksChanged = QtCore.pyqtSignal()                     # pri mazaní/čistení

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumSize(480, 360)
        self._img = None
        self._qimg = None
        self._pix = None
        self._scale = 1.0
        self._offx = 0
        self._offy = 0
        self._drag = False
        self._x0 = self._y0 = 0
        self._rect = None           # aktuálne kreslený obdĺžnik (x,y,w,h) v IMG súradniciach
        self._roi = None            # uložený ROI (x,y,w,h)
        self._masks = []            # zoznam masiek [(x,y,w,h), ...]
        self._mode = "roi"          # "roi" alebo "mask"

    # --- verejné API ---
    def set_mode(self, mode: str):
        self._mode = mode  # "roi" / "mask"
        self.update()

    def get_mode(self) -> str:
        return self._mode

    def set_ndarray(self, img):
        self._img = img
        if img is None:
            self._qimg = None; self._pix = None
            self.setText("—")
            return
        if img.ndim == 2:
            h,w = img.shape
            qimg = QtGui.QImage(img.data, w, h, w, QtGui.QImage.Format_Grayscale8)
        else:
            h,w,_ = img.shape
            qimg = QtGui.QImage(img.data, w, h, 3*w, QtGui.QImage.Format_BGR888)
        self._qimg = qimg.copy()
        self._update_pix()

    def set_roi(self, x,y,w,h):
        self._roi = (int(x),int(y),int(w),int(h))
        self.update()

    def clear_roi(self):
        self._roi = None
        self.update()

    def add_mask_rect(self, x,y,w,h):
        self._masks.append((int(x),int(y),int(w),int(h)))
        self.maskAdded.emit(int(x),int(y),int(w),int(h))
        self.update()

    def set_masks(self, rects):
        self._masks = [(int(x),int(y),int(w),int(h)) for (x,y,w,h) in rects]
        self.masksChanged.emit()
        self.update()

    def clear_masks(self):
        self._masks = []
        self.masksChanged.emit()
        self.update()

    def masks(self):
        return list(self._masks)

    # --- vnútorné ---
    def _update_pix(self):
        if self._qimg is None:
            return
        lblw, lblh = self.width(), self.height()
        imw, imh = self._qimg.width(), self._qimg.height()
        self._scale = min(lblw / imw, lblh / imh)
        dw = int(imw * self._scale)
        dh = int(imh * self._scale)
        self._offx = (lblw - dw) // 2
        self._offy = (lblh - dh) // 2
        self._pix = QtGui.QPixmap.fromImage(self._qimg).scaled(dw, dh, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_pix()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._pix:
            p = QtGui.QPainter(self)
            p.drawPixmap(self._offx, self._offy, self._pix)

            # Maska(y)
            p.setPen(QtGui.QPen(COLOR_MASK, 2, QtCore.Qt.SolidLine))
            for (x,y,w,h) in self._masks:
                rx = int(self._offx + x*self._scale)
                ry = int(self._offy + y*self._scale)
                rw = int(w*self._scale)
                rh = int(h*self._scale)
                p.drawRect(rx, ry, rw, rh)

            # ROI
            if self._roi:
                x,y,w,h = self._roi
                rx = int(self._offx + x*self._scale)
                ry = int(self._offy + y*self._scale)
                rw = int(w*self._scale)
                rh = int(h*self._scale)
                p.setPen(QtGui.QPen(COLOR_ROI, 2, QtCore.Qt.SolidLine))
                p.drawRect(rx, ry, rw, rh)

            # práve kreslený obdĺžnik (podľa režimu meníme farbu)
            if self._rect:
                x,y,w,h = self._rect
                rx = int(self._offx + x*self._scale)
                ry = int(self._offy + y*self._scale)
                rw = int(w*self._scale)
                rh = int(h*self._scale)
                color = COLOR_ROI if self._mode=="roi" else COLOR_MASK
                p.setPen(QtGui.QPen(color, 2, QtCore.Qt.DashLine))
                p.drawRect(rx, ry, rw, rh)
            p.end()

    def mousePressEvent(self, ev: QtGui.QMouseEvent):
        if self._img is None or self._qimg is None: return
        if ev.button() == QtCore.Qt.LeftButton:
            ix, iy = self._widget_to_image(ev.x(), ev.y())
            if ix is None: return
            self._drag = True
            self._x0, self._y0 = ix, iy
            self._rect = (ix, iy, 1, 1)
            self.update()

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent):
        if not self._drag: return
        ix, iy = self._widget_to_image(ev.x(), ev.y())
        if ix is None: return
        x1 = min(self._x0, ix); y1 = min(self._y0, iy)
        x2 = max(self._x0, ix); y2 = max(self._y0, iy)
        w = max(1, x2 - x1); h = max(1, y2 - y1)
        self._rect = (x1, y1, w, h)
        self.update()

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent):
        if self._drag:
            self._drag = False
            if self._rect:
                x,y,w,h = self._rect
                if self._mode == "roi":
                    self._roi = (x,y,w,h)
                    self.roiChanged.emit(int(x), int(y), int(w), int(h))
                else:
                    self.add_mask_rect(x,y,w,h)
            self._rect = None
            self.update()

    def _widget_to_image(self, px, py):
        if self._qimg is None: return (None, None)
        x = px - self._offx
        y = py - self._offy
        if x < 0 or y < 0 or x >= self._pix.width() or y >= self._pix.height():
            return (None, None)
        ix = int(x / self._scale)
        iy = int(y / self._scale)
        ix = max(0, min(self._qimg.width()-1, ix))
        iy = max(0, min(self._qimg.height()-1, iy))
        return (ix, iy)
