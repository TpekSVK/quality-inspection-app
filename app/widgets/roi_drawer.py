# app/widgets/roi_drawer.py
from PyQt5 import QtWidgets, QtGui, QtCore

COLOR_ROI = QtGui.QColor(33, 150, 243)     # modrá
COLOR_MASK = QtGui.QColor(156, 39, 176)    # fialová
HANDLE_SIZE = 7

def _rect_handles(x,y,w,h):
    # rohy + stredy strán (8 bodov)
    cx, cy = x + w//2, y + h//2
    return {
        "tl": (x, y), "tr": (x+w, y),
        "bl": (x, y+h), "br": (x+w, y+h),
        "t": (cx, y), "b": (cx, y+h),
        "l": (x, cy), "r": (x+w, cy),
    }

def _hit_handle(px, py, handles, tol=8):
    for k,(hx,hy) in handles.items():
        if abs(px-hx) <= tol and abs(py-hy) <= tol:
            return ("resize", k)
    return (None, None)

def _hit_rect(px, py, x,y,w,h):
    return (x <= px <= x+w) and (y <= py <= y+h)

class ROIDrawer(QtWidgets.QLabel):
    roiChanged = QtCore.pyqtSignal(int, int, int, int)       # x,y,w,h
    maskAdded = QtCore.pyqtSignal(int, int, int, int)        # x,y,w,h
    masksChanged = QtCore.pyqtSignal()

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

        self._mode = "roi"          # "roi" alebo "mask"
        self._roi = None            # (x,y,w,h)
        self._masks = []            # [(x,y,w,h), ...]
        self._active_mask = -1      # index do self._masks

        # interakcia
        self._dragging = False
        self._op = None             # "move" / "resize"
        self._op_key = None         # ktorý roh/strana pri resize
        self._anchor = (0,0)        # v image súradniciach
        self._start_rect = None     # pôvodný rect pri začatí

    # ---------- Verejné API ----------
    def set_mode(self, mode: str):
        self._mode = mode
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

    def set_masks(self, rects):
        self._masks = [(int(x),int(y),int(w),int(h)) for (x,y,w,h) in rects]
        self._active_mask = -1 if not self._masks else 0
        self.masksChanged.emit()
        self.update()

    def masks(self):
        return list(self._masks)

    def add_mask_rect(self, x,y,w,h):
        self._masks.append((int(x),int(y),int(w),int(h)))
        self._active_mask = len(self._masks)-1
        self.maskAdded.emit(int(x),int(y),int(w),int(h))
        self.update()

    def clear_masks(self):
        self._masks = []
        self._active_mask = -1
        self.masksChanged.emit()
        self.update()

    def set_active_mask_index(self, idx: int):
        if 0 <= idx < len(self._masks):
            self._active_mask = idx
        else:
            self._active_mask = -1
        self.update()

    # ---------- Internal ----------
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
        if not self._pix:
            return
        p = QtGui.QPainter(self)
        p.drawPixmap(self._offx, self._offy, self._pix)

        def draw_rect_and_handles(rect, color, thick=2, active=False):
            x,y,w,h = rect
            rx = int(self._offx + x*self._scale)
            ry = int(self._offy + y*self._scale)
            rw = int(w*self._scale)
            rh = int(h*self._scale)
            p.setPen(QtGui.QPen(color, thick, QtCore.Qt.SolidLine))
            p.drawRect(rx, ry, rw, rh)
            # handles
            hs = max(5, int(HANDLE_SIZE * self._scale))
            handles = _rect_handles(rx, ry, rw, rh)
            for (hx,hy) in handles.values():
                r = QtCore.QRect(hx - hs//2, hy - hs//2, hs, hs)
                fill = QtGui.QColor(color)
                fill.setAlpha(180 if active else 120)
                p.fillRect(r, fill)
                p.setPen(QtGui.QPen(QtGui.QColor(0,0,0,200), 1))
                p.drawRect(r)

        # Masky (fialové)
        for i,rect in enumerate(self._masks):
            draw_rect_and_handles(rect, COLOR_MASK, thick=2, active=(i==self._active_mask))

        # ROI (modrá)
        if self._roi:
            draw_rect_and_handles(self._roi, COLOR_ROI, thick=2, active=(self._mode=="roi"))

        p.end()

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

    # ----- Mouse interakcia s úchytmi -----
    def mousePressEvent(self, ev: QtGui.QMouseEvent):
        if self._qimg is None: return
        if ev.button() != QtCore.Qt.LeftButton: return
        ix, iy = self._widget_to_image(ev.x(), ev.y())
        if ix is None: return

        target_rect = None
        target_type = None  # "roi" / "mask"
        # hit test – najprv masky (ak sme v mask režime), inak ROI
        if self._mode == "mask" and self._active_mask >= 0 and self._active_mask < len(self._masks):
            mx,my,mw,mh = self._masks[self._active_mask]
            handles = _rect_handles(mx,my,mw,mh)
            op, key = _hit_handle(ix, iy, handles)
            if op:
                target_rect = (mx,my,mw,mh); target_type="mask"; self._op=op; self._op_key=key
            elif _hit_rect(ix, iy, mx, my, mw, mh):
                target_rect = (mx,my,mw,mh); target_type="mask"; self._op="move"; self._op_key=None

        if target_rect is None and self._mode == "roi" and self._roi:
            rx,ry,rw,rh = self._roi
            handles = _rect_handles(rx,ry,rw,rh)
            op, key = _hit_handle(ix, iy, handles)
            if op:
                target_rect = (rx,ry,rw,rh); target_type="roi"; self._op=op; self._op_key=key
            elif _hit_rect(ix, iy, rx, ry, rw, rh):
                target_rect = (rx,ry,rw,rh); target_type="roi"; self._op="move"; self._op_key=None

        # ak nič netrafíme a sme v mask režime -> začni kresliť novú masku dragom
        if target_rect is None and self._mode == "mask":
            self._op = "draw"
            self._start_rect = (ix, iy, 1, 1)
            self._dragging = True
            self._anchor = (ix, iy)
            return

        if target_rect is not None:
            self._start_rect = target_rect
            self._dragging = True
            self._anchor = (ix, iy)
            self._target_type = target_type

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent):
        if not self._dragging: return
        ix, iy = self._widget_to_image(ev.x(), ev.y())
        if ix is None: return

        x0,y0,w0,h0 = self._start_rect
        dx = ix - self._anchor[0]
        dy = iy - self._anchor[1]

        def clamp_rect(x,y,w,h):
            H = self._qimg.height(); W = self._qimg.width()
            x = max(0, min(W-1, x))
            y = max(0, min(H-1, y))
            w = max(1, min(W - x, w))
            h = max(1, min(H - y, h))
            return x,y,w,h

        if self._op == "move":
            nx, ny = x0 + dx, y0 + dy
            rect = clamp_rect(nx, ny, w0, h0)
        elif self._op == "resize":
            nx, ny, nw, nh = x0, y0, w0, h0
            if self._op_key in ("tl","l","bl"):
                nx = x0 + dx; nw = w0 - dx
            if self._op_key in ("tl","t","tr"):
                ny = y0 + dy; nh = h0 - dy
            if self._op_key in ("tr","r","br"):
                nw = w0 + dx
            if self._op_key in ("bl","b","br"):
                nh = h0 + dy
            rect = clamp_rect(nx, ny, nw, nh)
        elif self._op == "draw":
            x1 = min(self._anchor[0], ix); y1 = min(self._anchor[1], iy)
            x2 = max(self._anchor[0], ix); y2 = max(self._anchor[1], iy)
            rect = clamp_rect(x1, y1, x2-x1, y2-y1)
        else:
            return

        if self._target_type == "roi":
            self._roi = rect
        elif self._target_type == "mask":
            if 0 <= self._active_mask < len(self._masks):
                self._masks[self._active_mask] = rect
        else:
            # draw -> dočasne do ničho; pri release pridáme
            self._temp_rect = rect
        self.update()

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent):
        if not self._dragging: return
        self._dragging = False
        if self._op == "draw" and hasattr(self, "_temp_rect"):
            x,y,w,h = self._temp_rect
            self.add_mask_rect(x,y,w,h)
            del self._temp_rect
        if self._target_type == "roi" and self._roi:
            x,y,w,h = self._roi
            self.roiChanged.emit(int(x),int(y),int(w),int(h))
        self._op = None
        self._op_key = None
