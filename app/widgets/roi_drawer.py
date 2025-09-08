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

    NOVINKY:
      - Zoom na koliesko myši (zoomuje na kurzor, nevycentruje ťa naspäť)
      - Pan (pravé alebo stredné tlačidlo myši)
      - Tlačidlá v rohu: + / − / Fit
    """
    roiChanged = QtCore.pyqtSignal(int, int, int, int)     # x,y,w,h
    maskAdded = QtCore.pyqtSignal(int, int, int, int)      # x,y,w,h
    masksChanged = QtCore.pyqtSignal()                     # pri mazaní/čistení
    shapeChanged = QtCore.pyqtSignal(dict)                 # {"shape":..., ...}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumSize(480, 360)
        self._show_overlays = True

        self.setStyleSheet("QLabel{background:#111; color:#bbb;}")

        # obrázok a odvodené dáta
        self._img = None
        self._qimg = None
        self._pix = None

        # transformácia obraz -> widget
        self._scale = 1.0        # aktuálna mierka = _base_scale * _zoom_factor
        self._base_scale = 1.0   # fit-to-window mierka (prepočíta sa v _update_pix)
        self._zoom_factor = 1.0  # relatívny zoom nad fit-to-window (1.0 = fit)
        self._fit_mode = True    # ak True, centrovanie drží „fit“. Pri zoom/pan sa vypne.
        self._offx = 0
        self._offy = 0

        # pan stav
        self._panning = False
        self._pan_start = None

        # interakčný stav kreslenia
        self._drag = False
        self._x0 = self._y0 = 0
        self._rect = None           # dočasný obdĺžnik (x,y,w,h) v IMG súradniciach

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

        # LINE: 2-klik režim (klik začiatok → klik koniec)
        self._line_two_click = False
        self._line_first = None     # (x,y) prvého kliku pri 2-klik móde

        # polyline rozpracované body
        self._poly_points = []      # [(x,y), ...] počas kreslenia polyline

        # --- UI: rohové tlačidlá + / − / Fit ---
        self._btn_zoom_in = QtWidgets.QPushButton("+", self); self._btn_zoom_in.setFixedSize(28, 24)
        self._btn_zoom_out = QtWidgets.QPushButton("−", self); self._btn_zoom_out.setFixedSize(28, 24)
        self._btn_fit = QtWidgets.QPushButton("Fit", self);   self._btn_fit.setFixedSize(36, 24)
        for b in (self._btn_zoom_in, self._btn_zoom_out, self._btn_fit):
            b.setFocusPolicy(QtCore.Qt.NoFocus)
            b.setStyleSheet(
                "QPushButton{background:#222;color:#ddd;border:1px solid #444;border-radius:4px;}"
                "QPushButton:hover{background:#333;}"
            )
        self._btn_zoom_in.clicked.connect(lambda: self._zoom_step(+1))
        self._btn_zoom_out.clicked.connect(lambda: self._zoom_step(-1))
        self._btn_fit.clicked.connect(self.reset_view)

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
        if mode != "line":
            self._line_first = None
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

    def set_line_two_click(self, enabled: bool):
        """Zapne/vypne '2-klik' kreslenie čiary (klik začiatok → klik koniec)."""
        self._line_two_click = bool(enabled)
        # reset rozkreslených stavov
        self._drag = False
        self._tmp_shape = None
        self._line_first = None
        self.update()


    def set_ndarray(self, img):
        """Nastaví zobrazený obraz (numpy ndarray). Resetne fit, ale zachová mód a kreslenie."""
        self._img = img
        if img is None:
            self._qimg = None; self._pix = None
            self.setText("—")
            self.update()
            return
        if img.ndim == 2:
            h, w = img.shape
            qimg = QtGui.QImage(img.data, w, h, w, QtGui.QImage.Format_Grayscale8)
        else:
            h, w, _ = img.shape
            qimg = QtGui.QImage(img.data, w, h, 3*w, QtGui.QImage.Format_BGR888)
        self._qimg = qimg.copy()

        # pri novom obrázku defaultne fitni
        self._zoom_factor = 1.0
        self._fit_mode = True
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

        # fit-to-window základ
        self._base_scale = min(lblw / imw, lblh / imh) if (imw > 0 and imh > 0) else 1.0
        self._scale = self._base_scale * self._zoom_factor

        dw = int(max(1, imw * self._scale))
        dh = int(max(1, imh * self._scale))

        # len v režime fit centrovať; inak zachovať manuálny offset
        if self._fit_mode:
            self._offx = (lblw - dw) // 2
            self._offy = (lblh - dh) // 2

        self._pix = QtGui.QPixmap.fromImage(self._qimg).scaled(
            dw, dh, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
        )
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_pix()
        # rozloženie tlačidiel do ľavého horného rohu s malým odsadením
        pad = 8
        x = pad; y = pad
        self._btn_zoom_in.move(x, y)
        self._btn_zoom_out.move(x + self._btn_zoom_in.width() + 6, y)
        self._btn_fit.move(x + self._btn_zoom_in.width() + self._btn_zoom_out.width() + 12, y)
        for b in (self._btn_zoom_in, self._btn_zoom_out, self._btn_fit):
            b.raise_()

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

            # --- Shape (žltý) – hotový + dočasný ---
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

    # ----------------- Zoom & Pan -----------------

    def wheelEvent(self, ev: QtGui.QWheelEvent):
        """Zoom na kurzor – bod pod kolieskom ostáva na mieste."""
        if self._qimg is None:
            return
        wx, wy = ev.x(), ev.y()
        ix, iy = self._widget_to_image(wx, wy)

        # cieľový faktor
        factor = 1.25 if ev.angleDelta().y() > 0 else (1.0 / 1.25)
        new_zoom = max(0.1, min(10.0, self._zoom_factor * factor))
        self._fit_mode = False

        if ix is None:
            # mimo pixmapy – zoom okolo stredu
            self._zoom_factor = new_zoom
            self._update_pix()
            return

        # prepočet tak, aby (ix,iy) ostal pod (wx,wy)
        self._zoom_factor = new_zoom
        lblw, lblh = self.width(), self.height()
        imw, imh = self._qimg.width(), self._qimg.height()
        self._base_scale = min(lblw / imw, lblh / imh) if (imw > 0 and imh > 0) else 1.0
        self._scale = self._base_scale * self._zoom_factor

        # wx = offx + ix * scale  => offx = wx - ix*scale
        self._offx = int(wx - ix * self._scale)
        self._offy = int(wy - iy * self._scale)

        # pregeneruj pixmapu na novú mierku (offset ponecháme)
        dw = int(max(1, imw * self._scale))
        dh = int(max(1, imh * self._scale))
        self._pix = QtGui.QPixmap.fromImage(self._qimg).scaled(
            dw, dh, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
        )
        self.update()

    def reset_view(self):
        """Reset na fit-to-window a centrovanie."""
        self._zoom_factor = 1.0
        self._fit_mode = True
        self._update_pix()

    def _zoom_step(self, direction: int):
        """Helper pre +/− tlačidlá – zoomuje okolo stredu widgetu."""
        if direction not in (+1, -1):
            return
        fake_delta = 120 if direction > 0 else -120
        cx = self.width() // 2
        cy = self.height() // 2
        ev = QtGui.QWheelEvent(
            QtCore.QPointF(cx, cy), QtCore.QPointF(cx, cy),
            QtCore.QPoint(0, fake_delta), QtCore.QPoint(0, fake_delta),
            fake_delta, QtCore.Qt.Vertical, QtCore.Qt.NoButton, QtCore.Qt.NoModifier
        )
        self.wheelEvent(ev)

    # ----------------- Mouse logika -----------------

    def _widget_to_image(self, px, py):
        if self._qimg is None or self._pix is None:
            return (None, None)
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

        # Pan pravým/stredným tlačidlom – len keď nekreslíme
        if ev.button() in (QtCore.Qt.MiddleButton, QtCore.Qt.RightButton):
            if not self._drag and self._mode not in ("polyline",):
                self._panning = True
                self._pan_start = ev.pos()
                self._fit_mode = False
                self.setCursor(QtCore.Qt.ClosedHandCursor)
                return

        # Polyline – pravým tlačidlom undo posledný bod
        if ev.button() == QtCore.Qt.RightButton and self._mode == "polyline":
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
            if self._line_two_click:
                # 2-klik: prvý klik nastaví začiatok, druhý klik ukončí
                if self._line_first is None:
                    self._line_first = (ix, iy)
                    self._tmp_shape = {"shape":"line", "pts":[[ix,iy],[ix,iy]], "width": self._stroke_width}
                    self.update()
                else:
                    x0, y0 = self._line_first
                    self._shape = {"shape":"line", "pts":[[x0,y0],[ix,iy]], "width": self._stroke_width}
                    self._line_first = None
                    self._tmp_shape = None
                    self.shapeChanged.emit(self._shape.copy())
                    self.update()
                return
            else:
                # klasika – ťahaním
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

        # panovanie
        if self._panning and self._pan_start is not None:
            dx = ev.x() - self._pan_start.x()
            dy = ev.y() - self._pan_start.y()
            self._offx += dx
            self._offy += dy
            self._pan_start = ev.pos()
            self._fit_mode = False
            self.update()
            return

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

        # LINE – 2-klik: ťahaj len náhľad
        if self._mode == "line" and self._line_two_click and self._line_first is not None and self._tmp_shape:
            self._tmp_shape["pts"][1] = [ix, iy]
            self.update()
            return

        # LINE – ťahaním
        if self._mode == "line" and self._drag and self._tmp_shape:
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

        # ukonči pan
        if ev.button() in (QtCore.Qt.MiddleButton, QtCore.Qt.RightButton):
            if self._panning:
                self._panning = False
                self.setCursor(QtCore.Qt.ArrowCursor)
                return

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
