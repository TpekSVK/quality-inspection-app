# app/widgets/image_view.py
from PyQt5 import QtWidgets, QtGui, QtCore
import numpy as np

class ImageView(QtWidgets.QLabel):
    clicked = QtCore.pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumSize(480, 360)
        self._qimg = None
        self.setStyleSheet("QLabel{background:#111; color:#bbb;}")

    def set_ndarray(self, img):
        if img is None:
            self.setText("—")
            return
        if img.ndim == 2:
            h,w = img.shape
            qimg = QtGui.QImage(img.data, w, h, w, QtGui.QImage.Format_Grayscale8)
        else:
            h,w,_ = img.shape
            qimg = QtGui.QImage(img.data, w, h, 3*w, QtGui.QImage.Format_BGR888)
        self._qimg = qimg.copy()
        pix = QtGui.QPixmap.fromImage(self._qimg).scaled(self.width(), self.height(), QtCore.Qt.KeepAspectRatio)
        self.setPixmap(pix)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._qimg is not None:
            pix = QtGui.QPixmap.fromImage(self._qimg).scaled(self.width(), self.height(), QtCore.Qt.KeepAspectRatio)
            self.setPixmap(pix)

    def mousePressEvent(self, ev: QtGui.QMouseEvent):
        if self._qimg is not None:
            self.clicked.emit(ev.x(), ev.y())
        super().mousePressEvent(ev)
