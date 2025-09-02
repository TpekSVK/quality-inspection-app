# app/tabs/teach_tab.py
from PyQt5 import QtWidgets, QtCore
import cv2 as cv
import json
from app.widgets.image_view import ImageView
from storage.recipe_store_json import RecipeStoreJSON

class TeachTab(QtWidgets.QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.store = RecipeStoreJSON()
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.view = ImageView()
        btn_load = QtWidgets.QPushButton("Načítať snímku (ako referenciu)")
        btn_save = QtWidgets.QPushButton("Uložiť referenciu do receptu...")
        self.edit_recipe = QtWidgets.QLineEdit("FORMA_X_PRODUCT_Y")
        form = QtWidgets.QFormLayout()
        form.addRow("Názov receptu:", self.edit_recipe)

        layout.addWidget(self.view)
        layout.addLayout(form)
        layout.addWidget(btn_load)
        layout.addWidget(btn_save)

        btn_load.clicked.connect(self.load_ref)
        btn_save.clicked.connect(self.save_recipe)

    def load_ref(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Vyber referenčný obrázok", "", "Obrázky (*.png *.jpg *.bmp)")
        if not path: return
        img = cv.imread(path, cv.IMREAD_GRAYSCALE)
        if img is None:
            QtWidgets.QMessageBox.critical(self, "Chyba", "Neviem načítať obrázok.")
            return
        self.ref_path = path
        self.view.set_ndarray(img)

    def save_recipe(self):
        name = self.edit_recipe.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Pozor", "Zadaj názov receptu.")
            return
        if not hasattr(self, "ref_path"):
            QtWidgets.QMessageBox.warning(self, "Pozor", "Najprv načítaj referenčný obrázok.")
            return
        # minimalistický recept
        recipe = {
            "meta": {"name": name},
            "reference_image": self.ref_path,
            "fixture": {"type":"template","tpl_xywh":[100,100,200,200],"min_score":0.6},
            "pxmm": None,
            "tools": [
                {"type":"diff_from_ref","name":"defects_roi_A",
                 "roi_xywh":[0,0,800,600],
                 "params":{"blur":3,"thresh":25,"morph_open":1,"min_blob_area":20,"measure":"area"},
                 "lsl":None,"usl":200.0,"units":"px"}
            ],
            "models": {},
            "plc": {"recipe_code":101}
        }
        self.store.save_version(name, recipe)
        QtWidgets.QMessageBox.information(self, "OK", f"Recept {name} uložený. Prepnúť do RUN/Builder a načítať.")
