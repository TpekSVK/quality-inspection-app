# app/tabs/builder_tab.py
from PyQt5 import QtWidgets, QtCore
import json
from storage.recipe_store_json import RecipeStoreJSON
from app.widgets.tool_value_panel import ToolValuePanel

class BuilderTab(QtWidgets.QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.store = RecipeStoreJSON()
        self._build()

    def _build(self):
        main = QtWidgets.QHBoxLayout(self)

        # ľavý: katalóg toolov
        left = QtWidgets.QVBoxLayout()
        self.list_tools = QtWidgets.QListWidget()
        for t in ["diff_from_ref","presence_absence","yolo_roi"]:
            self.list_tools.addItem(t)
        btn_add = QtWidgets.QPushButton("Pridať tool do receptu")
        left.addWidget(QtWidgets.QLabel("Katalóg nástrojov:"))
        left.addWidget(self.list_tools)
        left.addWidget(btn_add)

        # stred: výpis toolov v recepte
        mid = QtWidgets.QVBoxLayout()
        self.edit_recipe = QtWidgets.QLineEdit(self.state.current_recipe or "FORMA_X_PRODUCT_Y")
        self.list_recipe_tools = QtWidgets.QListWidget()
        btn_load = QtWidgets.QPushButton("Načítať recept")
        btn_save = QtWidgets.QPushButton("Uložiť recept (nová verzia)")
        mid.addWidget(QtWidgets.QLabel("Recept:"))
        mid.addWidget(self.edit_recipe)
        mid.addWidget(self.list_recipe_tools)
        mid.addWidget(btn_load)
        mid.addWidget(btn_save)

        # pravý: SZH panel
        right = QtWidgets.QVBoxLayout()
        self.szh = ToolValuePanel(units="px")
        right.addWidget(QtWidgets.QLabel("Měřeno / Spodní / Horní"))
        right.addWidget(self.szh)
        right.addStretch()

        main.addLayout(left,1)
        main.addLayout(mid,1)
        main.addLayout(right,1)

        btn_add.clicked.connect(self.add_tool)
        btn_load.clicked.connect(self.load_recipe)
        btn_save.clicked.connect(self.save_recipe)

        self.load_recipe()

    def load_recipe(self):
        name = self.edit_recipe.text().strip()
        try:
            self.recipe = self.store.load(name)
        except Exception as e:
            self.recipe = {"tools":[]}
        self.list_recipe_tools.clear()
        for t in self.recipe.get("tools",[]):
            self.list_recipe_tools.addItem(f"{t.get('type')} :: {t.get('name')} :: ROI={t.get('roi_xywh')} :: LSL={t.get('lsl')} :: USL={t.get('usl')}")
        self.szh.set_limits(None, None)
        self.szh.set_measured(0.0, True)

    def save_recipe(self):
        name = self.edit_recipe.text().strip()
        self.store.save_version(name, self.recipe)
        QtWidgets.QMessageBox.information(self, "OK", f"Recept {name} uložený.")
        # obnov AppState pipeline (ak beží)
        try:
            self.state.build_from_recipe(name)
        except: pass

    def add_tool(self):
        typ_item = self.list_tools.currentItem()
        if not typ_item: return
        typ = typ_item.text()
        # minimal: pridáme s default ROI a limitmi
        new_tool = {
            "type": typ,
            "name": f"{typ}_auto",
            "roi_xywh": [0,0,400,300],
            "params": {},
            "lsl": None,
            "usl": None,
            "units": "px"
        }
        self.recipe.setdefault("tools", []).append(new_tool)
        self.load_recipe()
