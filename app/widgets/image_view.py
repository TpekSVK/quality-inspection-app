# app/widgets/image_view.py
from PyQt5 import QtWidgets, QtGui, QtCore
import numpy as np

class ImageView(QtWidgets.QLabel):
    """
    ELI5: Toto je obyčajný zobrazovač obrázka do RUN tabu, ale s komfortom:
      - Zoom kolieskom myši priamo NA KURZOR (nevycentruje ťa naspäť)
      - Pan posun (pravé alebo stredné tlačidlo myši)
      - Rohové tlačidlá: +  −  Fit
    Žiadne kreslenie – len pozeranie. Preto to nič nerozbije v RUN.

    Signály:
      clicked(x, y) – nechávam kompatibilitu s pôvodom (emitne pozíciu kliknutia vo widgete)
    """
    clicked = QtCore.pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumSize(480, 360)
        self.setStyleSheet("QLabel{background:#111; color:#bbb;}")

        # interné dáta
        self._qimg: QtGui.QImage | None = None
        self._pix:  QtGui.QPixmap | None = None

        # transformácia (obraz -> widget)
        self._base_scale = 1.0   # fit-to-window mierka
        self._zoom_factor = 1.0  # relatívny zoom k fitu
        self._scale = 1.0        # výsledná mierka = base * zoom
        self._offx = 0           # posun pixmapy vo widgete
        self._offy = 0
        self._fit_mode = True    # ak je True, držíme centrovanie (klasický fit)

        # pan stav
        self._panning = False
        self._pan_start: QtCore.QPoint | None = None

        # UI rohové tlačidlá
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

    def set_ndarray(self, img: np.ndarray | None):
        """Prijme numpy obraz (BGR alebo GRAY), bez kreslenia overlayov (to sa deje inde)."""
        if img is None:
            self._qimg = None
            self._pix = None
            self.setText("—")
            self.update()
            return

        if img.ndim == 2:
            h, w = img.shape
            qimg = QtGui.QImage(img.data, w, h, w, QtGui.QImage.Format_Grayscale8)
        else:
            h, w, _ = img.shape
            # očakávame BGR (OpenCV)
            qimg = QtGui.QImage(img.data, w, h, 3*w, QtGui.QImage.Format_BGR888)

        # spravíme vlastnú kópiu aby buffer žil
        self._qimg = qimg.copy()

        # Zachovaj zoom/pan, ak sa NEzmenilo rozlíšenie
        prev_size = None
        if isinstance(getattr(self, "_qimg", None), QtGui.QImage) and not self._qimg.isNull():
            prev_size = (self._qimg.width(), self._qimg.height())

        # nastav nový QImage
        self._qimg = qimg.copy()

        same_size = (prev_size is not None and prev_size == (w, h))

        if same_size:
            # nič nereštartuj – nechaj aktuálny _zoom_factor, _offx/_offy, _fit_mode
            self._rebuild_pixmap()
        else:
            # ak sa zmenilo rozlíšenie, sprav čistý FIT
            self._zoom_factor = 1.0
            self._fit_mode = True
            self._offx = 0
            self._offy = 0
            self._rebuild_pixmap()


    def image_size(self) -> tuple[int, int] | None:
        if self._qimg is None:
            return None
        return (self._qimg.width(), self._qimg.height())

    def reset_view(self):
        """Fit-to-window + centrovanie."""
        self._zoom_factor = 1.0
        self._fit_mode = True
        self._rebuild_pixmap()

    # ------------- Interné -------------

    def _rebuild_pixmap(self):
        """Prepočíta mierku, offsety a vygeneruje _pix pre aktuálne okno."""
        if self._qimg is None:
            self._pix = None
            self.setPixmap(QtGui.QPixmap())  # clear
            return

        lblw, lblh = self.width(), self.height()
        imw, imh = self._qimg.width(), self._qimg.height()

        # fit-to-window základná mierka
        self._base_scale = min(lblw / imw, lblh / imh) if (imw > 0 and imh > 0) else 1.0
        self._scale = self._base_scale * self._zoom_factor

        # veľkosť vykreslenej pixmapy
        dw = int(max(1, imw * self._scale))
        dh = int(max(1, imh * self._scale))

        # pri fit móde centrovanie
        if self._fit_mode:
            self._offx = (lblw - dw) // 2
            self._offy = (lblh - dh) // 2

        self._pix = QtGui.QPixmap.fromImage(self._qimg).scaled(
            dw, dh, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
        )
        self.update()

    def _widget_to_image(self, px: int, py: int) -> tuple[int | None, int | None]:
        """Prevedie pozíciu vo widgete na súradnice v obrázku (clamp + mimo = None)."""
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

    # ------------- Events -------------

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self._pix:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        p.drawPixmap(self._offx, self._offy, self._pix)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rebuild_pixmap()
        # rozloženie rohových tlačidiel (ľavý horný roh)
        pad = 8
        x = pad; y = pad
        self._btn_zoom_in.move(x, y)
        self._btn_zoom_out.move(x + self._btn_zoom_in.width() + 6, y)
        self._btn_fit.move(x + self._btn_zoom_in.width() + self._btn_zoom_out.width() + 12, y)
        for b in (self._btn_zoom_in, self._btn_zoom_out, self._btn_fit):
            b.raise_()

    def mousePressEvent(self, ev: QtGui.QMouseEvent):
        # kompatibilita signálu
        self.clicked.emit(ev.x(), ev.y())

        # pan: pravé/stredné tlačidlo
        if ev.button() in (QtCore.Qt.MiddleButton, QtCore.Qt.RightButton):
            if self._qimg is not None:
                self._panning = True
                self._pan_start = ev.pos()
                self._fit_mode = False
                self.setCursor(QtCore.Qt.ClosedHandCursor)
                return
        return super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent):
        if self._panning and self._pan_start is not None:
            dx = ev.x() - self._pan_start.x()
            dy = ev.y() - self._pan_start.y()
            self._offx += dx
            self._offy += dy
            self._pan_start = ev.pos()
            self._fit_mode = False
            self.update()
            return
        return super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() in (QtCore.Qt.MiddleButton, QtCore.Qt.RightButton):
            if self._panning:
                self._panning = False
                self.setCursor(QtCore.Qt.ArrowCursor)
                return
        return super().mouseReleaseEvent(ev)

    def wheelEvent(self, ev: QtGui.QWheelEvent):
        """Zoom na kurzor – udržíme bod pod kolieskom na tom istom mieste na obrazovke."""
        if self._qimg is None:
            return

        wx, wy = ev.x(), ev.y()
        ix, iy = self._widget_to_image(wx, wy)

        factor = 1.25 if ev.angleDelta().y() > 0 else (1.0 / 1.25)
        new_zoom = max(0.1, min(10.0, self._zoom_factor * factor))
        self._fit_mode = False

        if ix is None:
            # mimo pixmapy – zoom okolo stredu
            self._zoom_factor = new_zoom
            self._rebuild_pixmap()
            return

        # vypočítaj mierku na základe nového zoomu
        self._zoom_factor = new_zoom

        lblw, lblh = self.width(), self.height()
        imw, imh = self._qimg.width(), self._qimg.height()
        self._base_scale = min(lblw / imw, lblh / imh) if (imw > 0 and imh > 0) else 1.0
        self._scale = self._base_scale * self._zoom_factor

        # chceme: wx = offx + ix * scale  => offx = wx - ix*scale (a rovnako y)
        self._offx = int(wx - ix * self._scale)
        self._offy = int(wy - iy * self._scale)

        # vygeneruj pixmapu pre novú mierku (offsety nechaj)
        dw = int(max(1, imw * self._scale))
        dh = int(max(1, imh * self._scale))
        self._pix = QtGui.QPixmap.fromImage(self._qimg).scaled(
            dw, dh, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
        )
        self.update()

    # ------------- Helpery -------------

    def _zoom_step(self, direction: int):
        """Klik na +/− tlačidlo: simulujeme wheelEvent okolo stredu."""
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
