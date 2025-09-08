# app/widgets/recipe_picker.py
from PyQt5 import QtWidgets, QtCore
from storage.recipe_store_json import RecipeStoreJSON
from pathlib import Path

class RecipePicker(QtWidgets.QWidget):
    """
    ELI5: Combo s editáciou + tlačidlo Obnoviť.
    - Vyber existujúci recept zo zoznamu, alebo dopíš nový názov (editable).
    - Emituje signál changed(name) pri zmene výberu/textu.
    """
    changed = QtCore.pyqtSignal(str)

    def __init__(self, initial: str = "", parent=None):
        super().__init__(parent)
        self.store = RecipeStoreJSON()

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.combo = QtWidgets.QComboBox()
        self.combo.setEditable(True)
        self.btn_refresh = QtWidgets.QToolButton()
        self.btn_refresh.setText("↻")
        self.btn_refresh.setToolTip("Obnoviť zoznam receptov")
        lay.addWidget(self.combo, 1)
        lay.addWidget(self.btn_refresh, 0)

        self.btn_refresh.clicked.connect(self.refresh)
        self.combo.currentIndexChanged.connect(self._emit_changed)
        self.combo.editTextChanged.connect(self._emit_changed)

        self.refresh()
        if initial:
            self.set_current(initial)

    # --- API ---
    def refresh(self):
        cur = self.combo.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        names = self._list_names()
        self.combo.addItems(names)
        # ponechaj text, ak bol „nový“
        if cur and cur not in names:
            self.combo.setEditText(cur)
        self.combo.blockSignals(False)
        self._emit_changed()

    def current(self) -> str:
        return (self.combo.currentText() or "").strip()

    def set_current(self, name: str):
        name = (name or "").strip()
        self.combo.blockSignals(True)
        idx = self.combo.findText(name)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        else:
            self.combo.setEditText(name)
        self.combo.blockSignals(False)
        self._emit_changed()

    # --- interné ---
    def _list_names(self):
        try:
            return self.store.list_names()
        except Exception:
            # fallback – prelistuj priečinok „recipes“
            root = Path(getattr(self.store, "root", "recipes"))
            if not root.exists():
                return []
            return sorted([p.name for p in root.iterdir() if p.is_dir()])

    def _emit_changed(self, *args):
        self.changed.emit(self.current())
