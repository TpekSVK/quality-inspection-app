# app/widgets/calibration_dialog.py
from PyQt5 import QtWidgets, QtCore, QtGui
import cv2 as cv
import numpy as np
from core.calibration import calibrate_two_points
from storage.recipe_store_json import RecipeStoreJSON

class CalibrationDialog(QtWidgets.QDialog):
    def __init__(self, recipe_name: str, ref_image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Px→mm kalibrácia (2 body)")
        self.recipe_name = recipe_name
        self.ref_path = ref_image_path
        self.store = RecipeStoreJSON()
        self._pt = []
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.lbl = QtWidgets.QLabel("Klikni na dva body rovnakej vzdialenosti, potom zadaj mm.")
        self.view = QtWidgets.QLabel()
        self.view.setAlignment(QtCore.Qt.AlignCenter)
        self.view.setMinimumSize(640, 480)
        self.mm_edit = QtWidgets.QLineEdit("10.0")
        self.mm_edit.setValidator(QtGui.QDoubleValidator(0.0001, 1e6, 4))

        btn_load = QtWidgets.QPushButton("Načítať referenčný obrázok")
        btn_save = QtWidgets.QPushButton("Uložiť do receptu")

        form = QtWidgets.QFormLayout()
        form.addRow("Skutočná vzdialenosť [mm]:", self.mm_edit)

        layout.addWidget(self.lbl)
        layout.addWidget(self.view)
        layout.addLayout(form)
        layout.addWidget(btn_load)
        layout.addWidget(btn_save)

        btn_load.clicked.connect(self.load_img)
        btn_save.clicked.connect(self.save_to_recipe)
        self.view.mousePressEvent = self.on_click

        self.qimg = None
        self.img = None

    def load_img(self):
        img = cv.imread(self.ref_path, cv.IMREAD_GRAYSCALE)
        if img is None:
            QtWidgets.QMessageBox.critical(self, "Chyba", f"Neviem načítať {self.ref_path}")
            return
        self.img = img
        self._pt = []
        self._update_view()

    def _update_view(self):
        if self.img is None: return
        rgb = cv.cvtColor(self.img, cv.COLOR_GRAY2BGR)
        for p in self._pt:
            cv.circle(rgb, (p[0], p[1]), 5, (0,0,255), -1)
        h, w = rgb.shape[:2]
        qimg = QtGui.QImage(rgb.data, w, h, 3*w, QtGui.QImage.Format_BGR888)
        pix = QtGui.QPixmap.fromImage(qimg).scaled(self.view.width(), self.view.height(), QtCore.Qt.KeepAspectRatio)
        self.view.setPixmap(pix)

    def on_click(self, event):
        if self.img is None: return
        pix: QtGui.QPixmap = self.view.pixmap()
        if pix is None: return
        # spätné mapovanie kliknutia do obrázka
        label_w, label_h = self.view.width(), self.view.height()
        pix_w, pix_h = pix.width(), pix.height()
        off_x = (label_w - pix_w)//2
        off_y = (label_h - pix_h)//2
        x = event.pos().x() - off_x
        y = event.pos().y() - off_y
        if x < 0 or y < 0 or x >= pix_w or y >= pix_h: return
        # nájdeme scale, aby sme to vrátili do originálnych px
        h, w = self.img.shape[:2]
        scale = min(pix_w / w, pix_h / h)
        img_x = int(x / scale)
        img_y = int(y / scale)
        self._pt.append((img_x, img_y))
        if len(self._pt) > 2:
            self._pt = self._pt[-2:]
        self._update_view()

    def save_to_recipe(self):
        if self.img is None or len(self._pt) < 2:
            QtWidgets.QMessageBox.warning(self, "Pozor", "Vyber 2 body a načítaj obrázok.")
            return
        try:
            mm = float(self.mm_edit.text())
        except:
            QtWidgets.QMessageBox.warning(self, "Pozor", "Zadaj korektné mm.")
            return
        res = calibrate_two_points(self._pt[0], self._pt[1], mm)
        # načítame recept a uložíme mm_per_px
        recipe = self.store.load(self.recipe_name)
        recipe["pxmm"] = res
        self.store.save_version(self.recipe_name, recipe)
        QtWidgets.QMessageBox.information(self, "Hotovo", f"Uložené do receptu {self.recipe_name}:\n{res}")
