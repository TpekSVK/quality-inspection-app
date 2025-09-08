# app/widgets/roi_drawer.py
from PyQt5 import QtWidgets, QtGui, QtCore
import math
from config import ui_style as UI

COLOR_ROI   = QtGui.QColor(*UI.ROI_RGB)
COLOR_MASK  = QtGui.QColor(*UI.MASK_RGB)
COLOR_SHAPE = QtGui.QColor(*UI.SHAPE_RGB)


class ROIDrawer(QtWidgets.QLabel):
    """
    ELI5: Zobrazuje obrázok a umožňuje kresliť:
      - ROI (modrý obdĺžnik)
      - masky (fialové obdĺžniky)
      - tvary pre „edge trace“ nástroje: line / circle / polyline (žlté)
    """
    roiChanged = QtCore.pyqtSignal(int, int, int, int)     # x,y,w,h
    maskAdded = QtCore.pyqtSignal(int, int, int, int)      # x,y,w,h
    masksChanged = QtCore.pyqtSignal()                     # pri mazaní/čistení
    shapeChanged = QtCore.pyqtSignal(dict)                 # {"shape":..., ...}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumSize(480, 360)
        self._show_overlays = True  # <<< NOVÉ: ovládanie viditeľnosti ROI/masky

        self.setStyleSheet("QLabel{background:#111; color:#bbb;}")

        self._img = None
        self._qimg = None
        self._pix = None
        self._scale = 1.0
        self._offx = 0
        self._offy = 0

        # interakčný stav
        self._drag = False
        self._x0 = self._y0 = 0
        self._rect = None           # dočasne kreslený obdĺžnik (x,y,w,h) v IMG súradniciach

        # dáta ROI / masky
        self._roi = None            # uložený ROI (x,y,w,h)
        self._masks = []            # zoznam masiek [(x,y,w,h), ...]
        self._active_mask = -1

        # mód kreslenia: "roi" | "mask" | "line" | "circle" | "polyline"
        self._mode = "roi"

        # shape dáta pre line/circle/polyline
        self._shape = None          # dict: {"shape":"line"/"circle"/"polyline", ...}
        self._stroke_width = 3      # šírka profilu okolo linky (pre tooly)
        self._tmp_shape = None      # rozpracovaná kresba pre line/circle

        # polyline rozpracované body
        self._poly_points = []      # [(x,y), ...] počas kreslenia polyline

    # ------------- Verejné API -------------

    def set_mode(self, mode: str):
        """Prepne režim kreslenia."""
        if mode not in ("roi", "mask", "line", "circle", "polyline"):
            return
        self._mode = mode
        # pri začatí nového módu zruš rozkreslené dočasné veci
        self._drag = False
        self._rect = None
        self._tmp_shape = None
        if mode != "polyline":
            self._poly_points = []
        self.update()

    def get_mode(self) -> str:
        return self._mode

    def set_stroke_width(self, w: int):
        self._stroke_width = max(1, int(w))
        # aktualizuj shape, ak existuje
        if self._shape and "width" in self._shape:
            self._shape["width"] = self._stroke_width
            self.shapeChanged.emit(self._shape.copy())
        self.update()

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

    # --- ROI ---
    def set_roi(self, x,y,w,h):
        self._roi = (int(x),int(y),int(w),int(h))
        self.update()

    def clear_roi(self):
        self._roi = None
        self.update()

    # --- Masky ---
    def set_masks(self, rects):
        self._masks = [(int(x),int(y),int(w),int(h)) for (x,y,w,h) in rects]
        self._active_mask = -1 if not self._masks else 0
        self.masksChanged.emit()
        self.update()

    def set_show_overlays(self, show: bool):
        self._show_overlays = bool(show)
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

    # --- Shapes (line/circle/polyline) ---
    def get_shape(self) -> dict:
        """Vráti posledný nakreslený shape (dict) alebo None."""
        return None if self._shape is None else self._shape.copy()

    def set_shape(self, shape: dict):
        """Nastaví shape (napr. pri načítaní receptu) a prekreslí."""
        self._shape = None if not shape else dict(shape)
        # ak shape nemá width, doplň aktuálnu stroke_width
        if self._shape and "width" not in self._shape:
            self._shape["width"] = self._stroke_width
        self.update()

    # ------------- Interné -------------
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
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.drawPixmap(self._offx, self._offy, self._pix)

        # --- helper na transformáciu img->widget ---
        def iw(x, y):
            rx = int(self._offx + x*self._scale)
            ry = int(self._offy + y*self._scale)
            return rx, ry

        if self._show_overlays:
            # --- Masky (fialové) ---
            p.setPen(QtGui.QPen(COLOR_MASK, UI.PEN_THIN, QtCore.Qt.SolidLine))
            for (x,y,w,h) in self._masks:
                rx, ry = iw(x,y)
                rw = int(w*self._scale); rh = int(h*self._scale)
                p.drawRect(rx, ry, rw, rh)

            # --- ROI (modrý obdĺžnik) ---
            if self._roi:
                x,y,w,h = self._roi
                rx, ry = iw(x,y)
                rw = int(w*self._scale); rh = int(h*self._scale)
                p.setPen(QtGui.QPen(COLOR_ROI, UI.PEN_THICK, QtCore.Qt.SolidLine))                
                p.drawRect(rx, ry, rw, rh)

            # --- Shape (žltý) – najprv hotový shape, potom dočasný ---
            p.setPen(QtGui.QPen(COLOR_SHAPE, UI.PEN_THIN, QtCore.Qt.SolidLine))


            def draw_shape(shape):
                if not shape or "shape" not in shape: return
                s = shape.get("shape")
                if s == "line":
                    pts = shape.get("pts") or []
                    if len(pts) == 2:
                        (x1,y1),(x2,y2) = pts
                        ax, ay = iw(x1,y1); bx, by = iw(x2,y2)
                        p.drawLine(ax, ay, bx, by)
                elif s == "circle":
                    cx = shape.get("cx"); cy = shape.get("cy"); r = shape.get("r",0)
                    if cx is not None and cy is not None and r is not None and r > 0:
                        cwx, cwy = iw(cx, cy)
                        rw = int(r*self._scale)
                        rect = QtCore.QRect(cwx - rw, cwy - rw, 2*rw, 2*rw)
                        p.drawEllipse(rect)
                elif s == "polyline":
                    pts = shape.get("pts") or []
                    if len(pts) >= 2:
                        qpts = [QtCore.QPoint(*iw(x,y)) for (x,y) in pts]
                        for i in range(len(qpts)-1):
                            p.drawLine(qpts[i], qpts[i+1])

            # hotový shape
            draw_shape(self._shape)
            # rozkreslený dočasný shape (line/circle počas ťahania)
            if self._tmp_shape:
                pen = QtGui.QPen(COLOR_SHAPE, UI.PEN_THIN, QtCore.Qt.DashLine)
                p.setPen(pen)
                draw_shape(self._tmp_shape)

            # polyline – práve rozkresľované body
            if self._mode == "polyline" and self._poly_points:
                pen = QtGui.QPen(COLOR_SHAPE, 2, QtCore.Qt.DashLine)
                p.setPen(pen)
                qpts = [QtCore.QPoint(*iw(x,y)) for (x,y) in self._poly_points]
                for i in range(len(qpts)-1):
                    p.drawLine(qpts[i], qpts[i+1])
                # body
                brush = QtGui.QBrush(COLOR_SHAPE)
                for qp in qpts:
                    p.setBrush(brush)
                    p.drawEllipse(qp, 3, 3)

            # práve kreslený obdĺžnik (ROI/mask)
            if self._rect:
                x,y,w,h = self._rect
                rx, ry = iw(x,y)
                rw = int(w*self._scale); rh = int(h*self._scale)
                color = COLOR_ROI if self._mode=="roi" else COLOR_MASK
                p.setPen(QtGui.QPen(color, UI.PEN_THIN, QtCore.Qt.DashLine))

                p.drawRect(rx, ry, rw, rh)

    # ----------------- Mouse logika -----------------

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

    def mousePressEvent(self, ev: QtGui.QMouseEvent):
        if self._img is None or self._qimg is None:
            return super().mousePressEvent(ev)
        if ev.button() == QtCore.Qt.RightButton and self._mode == "polyline":
            # undo posledný bod
            if self._poly_points:
                self._poly_points.pop()
                self.update()
            return

        if ev.button() != QtCore.Qt.LeftButton:
            return super().mousePressEvent(ev)

        ix, iy = self._widget_to_image(ev.x(), ev.y())
        if ix is None:
            return super().mousePressEvent(ev)

        if self._mode in ("roi", "mask"):
            # klasika – obdĺžnik myšou
            self._drag = True
            self._x0, self._y0 = ix, iy
            self._rect = (ix, iy, 1, 1)
            self.update()
            return

        if self._mode == "line":
            # začiatok úsečky
            self._drag = True
            self._tmp_shape = {"shape":"line", "pts":[[ix,iy],[ix,iy]], "width": self._stroke_width}
            self.update()
            return

        if self._mode == "circle":
            # stred kruhu
            self._drag = True
            self._tmp_shape = {"shape":"circle", "cx": ix, "cy": iy, "r": 1, "width": self._stroke_width}
            self.update()
            return

        if self._mode == "polyline":
            # pridaj bod
            self._poly_points.append((ix, iy))
            self.update()
            return

        return super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent):
        if self._img is None or self._qimg is None:
            return super().mouseMoveEvent(ev)
        ix, iy = self._widget_to_image(ev.x(), ev.y())
        if ix is None:
            return super().mouseMoveEvent(ev)

        if self._mode in ("roi", "mask") and self._drag:
            x1 = min(self._x0, ix); y1 = min(self._y0, iy)
            x2 = max(self._x0, ix); y2 = max(self._y0, iy)
            w = max(1, x2 - x1); h = max(1, y2 - y1)
            self._rect = (x1, y1, w, h)
            self.update()
            return

        if self._mode == "line" and self._drag and self._tmp_shape:
            # update druhého bodu
            self._tmp_shape["pts"][1] = [ix, iy]
            self.update()
            return

        if self._mode == "circle" and self._drag and self._tmp_shape:
            # update polomeru
            cx, cy = self._tmp_shape["cx"], self._tmp_shape["cy"]
            r = int(math.hypot(ix - cx, iy - cy))
            self._tmp_shape["r"] = max(1, r)
            self.update()
            return

        return super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent):
        if self._img is None or self._qimg is None:
            return super().mouseReleaseEvent(ev)

        if ev.button() == QtCore.Qt.LeftButton:
            if self._mode in ("roi", "mask") and self._drag:
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
                return

            if self._mode == "line" and self._drag and self._tmp_shape:
                self._drag = False
                # finalizuj úsečku
                self._shape = dict(self._tmp_shape)
                self._tmp_shape = None
                self.shapeChanged.emit(self._shape.copy())
                self.update()
                return

            if self._mode == "circle" and self._drag and self._tmp_shape:
                self._drag = False
                # finalizuj kruh
                self._shape = dict(self._tmp_shape)
                self._tmp_shape = None
                self.shapeChanged.emit(self._shape.copy())
                self.update()
                return

        return super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev: QtGui.QMouseEvent):
        # ukončenie polyline dvojklikom (ľavý)
        if self._mode == "polyline" and ev.button() == QtCore.Qt.LeftButton and len(self._poly_points) >= 2:
            self._shape = {"shape":"polyline", "pts":[[x,y] for (x,y) in self._poly_points], "width": self._stroke_width}
            self._poly_points = []
            self.shapeChanged.emit(self._shape.copy())
            self.update()
            return
        return super().mouseDoubleClickEvent(ev)
