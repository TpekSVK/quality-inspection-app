# app/tabs/teach_tab.py
from PyQt5 import QtWidgets, QtCore
import cv2 as cv
import json
from pathlib import Path
from app.widgets.image_view import ImageView
from storage.recipe_store_json import RecipeStoreJSON

class TeachTab(QtWidgets.QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.store = RecipeStoreJSON()
        self.ref_path = None
        self.ref_img = None
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.view = ImageView()
        hl = QtWidgets.QHBoxLayout()
        btn_load = QtWidgets.QPushButton("Načítať snímku (ako referenciu)")
        btn_capture = QtWidgets.QPushButton("Zachytiť z kamery (referencia)")
        hl.addWidget(btn_load); hl.addWidget(btn_capture)

        btn_save = QtWidgets.QPushButton("Uložiť referenciu do receptu...")
        self.edit_recipe = QtWidgets.QLineEdit("FORMA_X_PRODUCT_Y")
        form = QtWidgets.QFormLayout()
        form.addRow("Názov receptu:", self.edit_recipe)

        layout.addWidget(self.view)
        layout.addLayout(form)
        layout.addLayout(hl)
        layout.addWidget(btn_save)

        btn_load.clicked.connect(self.load_ref)
        btn_capture.clicked.connect(self.capture_ref)
        btn_save.clicked.connect(self.save_recipe)

    def load_ref(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Vyber referenčný obrázok", "", "Obrázky (*.png *.jpg *.bmp)")
        if not path: return
        img = cv.imread(path, cv.IMREAD_GRAYSCALE)
        if img is None:
            QtWidgets.QMessageBox.critical(self, "Chyba", "Neviem načítať obrázok.")
            return
        self.ref_path = path
        self.ref_img = img
        self.view.set_ndarray(img)

    def capture_ref(self):
        if self.state.camera is None:
            QtWidgets.QMessageBox.warning(self, "Pozor", "Najprv v Nastaveniach vyber kameru a stlač 'Použiť'.")
            return
        img = self.state.get_frame(timeout_ms=300)
        if img is None:
            QtWidgets.QMessageBox.warning(self, "Pozor", "Z kamery neprišla snímka.")
            return
        self.ref_img = img
        self.ref_path = None  # bude sa ukladať pri save
        self.view.set_ndarray(img)

    def save_recipe(self):
        name = self.edit_recipe.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Pozor", "Zadaj názov receptu.")
            return
        if self.ref_img is None and not self.ref_path:
            QtWidgets.QMessageBox.warning(self, "Pozor", "Najprv načítaj alebo zachyť referenčný obrázok.")
            return

        # ak sme zachytili z kamery, uložíme do recipes/<name>/reference.png
        ref_path_final = self.ref_path
        if self.ref_img is not None and self.ref_path is None:
            d = Path("recipes")/name
            d.mkdir(parents=True, exist_ok=True)
            ref_path_final = str(d/"reference.png")
            cv.imwrite(ref_path_final, self.ref_img)

        recipe = {
            "meta": {"name": name},
            "reference_image": ref_path_final,
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
        QtWidgets.QMessageBox.information(self, "OK", f"Recept {name} uložený.")
