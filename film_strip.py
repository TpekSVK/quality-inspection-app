### film_strip.py
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QDialog
from PySide6.QtGui import QPixmap, QMouseEvent
from PySide6.QtCore import Qt, Signal
import os

class ClickableLabel(QLabel):
    double_clicked = Signal()
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.double_clicked.emit()

class FilmStripWidget(QWidget):
    def __init__(self, recent_photos_list, parent=None):
        """
        recent_photos_list: zoznam dvojíc (cesta_k_fotke, typ)
        typ = "OK" alebo "NOK"
        """
        super().__init__(parent)
        self.recent_photos = recent_photos_list

        # tmavé pozadie
        self.setStyleSheet("background-color: rgb(30,30,30);")

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.photos_layout = QHBoxLayout()
        self.labels = []
        for _ in range(6):
            lbl = ClickableLabel()
            lbl.setFixedSize(100, 100)
            lbl.setScaledContents(True)
            lbl.double_clicked.connect(lambda l=lbl: self.show_photo_fullscreen(l))
            self.labels.append(lbl)
            self.photos_layout.addWidget(lbl)
        self.layout.addLayout(self.photos_layout)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.valueChanged.connect(self.update_strip)
        self.layout.addWidget(self.slider)

    def update_strip(self):
        start_idx = self.slider.value()
        photos_to_show = self.recent_photos[start_idx:start_idx+6]
        for i in range(6):
            if i < len(photos_to_show):
                photo_path, photo_type = photos_to_show[i]
                if photo_path and os.path.exists(photo_path):
                    pixmap = QPixmap(photo_path)
                    self.labels[i].setPixmap(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    if photo_type == "OK":
                        self.labels[i].setStyleSheet("border: 2px solid green;")
                    else:
                        self.labels[i].setStyleSheet("border: 2px solid red;")
                else:
                    self.labels[i].clear()
                    self.labels[i].setStyleSheet("")
            else:
                self.labels[i].clear()
                self.labels[i].setStyleSheet("")
        self.slider.setMaximum(max(0, len(self.recent_photos)-6))

    def show_photo_fullscreen(self, label):
        try:
            idx = self.labels.index(label)
            photo_path, _ = self.recent_photos[self.slider.value() + idx]
        except (ValueError, IndexError):
            return

        if os.path.exists(photo_path):
            dialog = QDialog(self)
            dialog.setWindowTitle("Fotka - plné rozlíšenie")
            layout = QVBoxLayout()
            lbl = QLabel()
            pixmap = QPixmap(photo_path)  # načítaj originálny súbor
            lbl.setPixmap(pixmap)
            lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl)
            dialog.setLayout(layout)
            dialog.resize(pixmap.width(), pixmap.height())
            dialog.exec()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.update_strip()
            self.show()
