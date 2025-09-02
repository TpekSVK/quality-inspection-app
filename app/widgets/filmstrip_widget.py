# app/widgets/filmstrip_widget.py
from PyQt5 import QtWidgets, QtGui, QtCore

class FilmstripWidget(QtWidgets.QScrollArea):
    imageClicked = QtCore.pyqtSignal(int)  # index

    def __init__(self, parent=None, max_items=30):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._max = max_items
        self._thumbs = []

        self.container = QtWidgets.QWidget()
        self.layout = QtWidgets.QHBoxLayout(self.container)
        self.layout.addStretch()
        self.setWidget(self.container)

    def add_pixmap(self, pix: QtGui.QPixmap):
        lbl = QtWidgets.QLabel()
        lbl.setPixmap(pix.scaledToHeight(100, QtCore.Qt.SmoothTransformation))
        idx = len(self._thumbs)
        lbl.mousePressEvent = lambda e, i=idx: self.imageClicked.emit(i)
        self.layout.insertWidget(self.layout.count()-1, lbl)
        self._thumbs.append(lbl)
        if len(self._thumbs) > self._max:
            w = self._thumbs.pop(0)
            w.setParent(None)
