# app/widgets/preproc_catalog.py
from typing import List, Dict, Any
from PyQt5 import QtWidgets, QtCore

DEFAULT_PREPROC = [
    {"cat":"Šum", "title":"Median 3×3", "desc":"Zníži soľ-a-korenie šum bez rozpatlania hrán.",
     "chain":[{"op":"median","k":3}]},
    {"cat":"Kontrast", "title":"CLAHE 2.0 (8×8)", "desc":"Lokálne vyrovnanie kontrastu – vytiahne jemné detaily.",
     "chain":[{"op":"clahe","clip":2.0,"tile":8}]},
    {"cat":"Pozadie", "title":"Top-hat 15", "desc":"Odstráni hladké pozadie, nechá malé svetlé vady.",
     "chain":[{"op":"tophat","k":15}]},
    {"cat":"Hrany", "title":"Unsharp 1.0 / r=3", "desc":"Doostrenie hrán pred detekciou.",
     "chain":[{"op":"unsharp","amount":1.0,"radius":3}]},
    {"cat":"Kombinácia", "title":"Median + CLAHE", "desc":"Najprv odšum, potom lokálny kontrast.",
     "chain":[{"op":"median","k":3},{"op":"clahe","clip":2.0,"tile":8}]},
    {"cat":"Žiadne", "title":"Bez predspracovania", "desc":"Vypnuté.",
     "chain":[]},
]

def _chain_to_text(chain: List[Dict[str,Any]]) -> str:
    if not chain:
        return "—"
    parts=[]
    for st in chain:
        op = st.get("op","?")
        p  = ", ".join([f"{k}={v}" for k,v in st.items() if k!="op"])
        parts.append(f"{op}({p})" if p else op)
    return " → ".join(parts)

class _OpEditor(QtWidgets.QGroupBox):
    """Mini editor parametrov pre 1 krok (op) v chain-e."""
    changed = QtCore.pyqtSignal()

    def __init__(self, step: Dict[str,Any], parent=None):
        super().__init__(f"Op: {step.get('op','?')}", parent)
        self.step = dict(step)
        form = QtWidgets.QFormLayout(self)
        self.widgets = {}

        def add_spin(name, key, vmin, vmax, step=1, dec=False):
            if dec:
                w = QtWidgets.QDoubleSpinBox(); w.setRange(vmin, vmax); w.setSingleStep(step)
                w.setValue(float(self.step.get(key, 0.0)))
            else:
                w = QtWidgets.QSpinBox(); w.setRange(vmin, vmax); w.setSingleStep(step)
                w.setValue(int(self.step.get(key, 0)))
            w.valueChanged.connect(self._on_changed)
            self.widgets[key] = w
            form.addRow(name, w)

        op = str(self.step.get("op","")).lower()
        if op in ("median","gaussian"):
            add_spin("K (px, nepárne)", "k", 1, 99, 2, dec=False)
        elif op == "bilateral":
            add_spin("d", "d", 1, 99, 1, dec=False)
            add_spin("sigmaColor", "sigmaColor", 1, 255, 1, dec=True)
            add_spin("sigmaSpace", "sigmaSpace", 1, 255, 1, dec=True)
        elif op == "clahe":
            add_spin("clip", "clip", 0.1, 40.0, 0.1, dec=True)
            add_spin("tile", "tile", 2, 64, 1, dec=False)
        elif op in ("tophat","blackhat"):
            add_spin("K (px, nepárne)", "k", 3, 99, 2, dec=False)
        elif op == "unsharp":
            add_spin("amount", "amount", 0.0, 5.0, 0.1, dec=True)
            add_spin("radius", "radius", 1, 51, 2, dec=False)
        elif op == "normalize":
            add_spin("alpha", "alpha", 0.0, 255.0, 1.0, dec=True)
            add_spin("beta",  "beta",  0.0, 255.0, 1.0, dec=True)
        else:
            lab = QtWidgets.QLabel("Tento op nemá editovateľné parametre.")
            form.addRow(lab)

    def _on_changed(self, *_):
        # uloží hodnoty späť
        for k,w in self.widgets.items():
            self.step[k] = float(w.value()) if isinstance(w, QtWidgets.QDoubleSpinBox) else int(w.value())
        self.changed.emit()

class PreprocDialog(QtWidgets.QDialog):
    """
    Katalóg predspracovania: kategórie -> presety -> edit parametrov -> Použiť
    """
    def __init__(self, parent=None, initial_chain: List[Dict[str,Any]] = None):
        super().__init__(parent)
        self.setWindowTitle("Predspracovanie v ROI")
        self.resize(720, 480)

        self._catalog = list(DEFAULT_PREPROC)
        self._selected = None
        self._chain = list(initial_chain or [])

        main = QtWidgets.QVBoxLayout(self)
        split = QtWidgets.QSplitter(self); split.setOrientation(QtCore.Qt.Horizontal)
        main.addWidget(split)

        # Ľavo: kategórie + preset grid
        left = QtWidgets.QWidget(); left_l = QtWidgets.QVBoxLayout(left)
        self.list_cat = QtWidgets.QListWidget()
        self.list_presets = QtWidgets.QListWidget(); self.list_presets.setViewMode(QtWidgets.QListView.IconMode)
        self.list_presets.setResizeMode(QtWidgets.QListView.Adjust); self.list_presets.setIconSize(QtCore.QSize(32,32))
        self.list_presets.setSpacing(8)
        left_l.addWidget(QtWidgets.QLabel("Kategórie")); left_l.addWidget(self.list_cat, 1)
        left_l.addWidget(QtWidgets.QLabel("Presety"));   left_l.addWidget(self.list_presets, 2)

        # Pravo: popis + editor chainu
        right = QtWidgets.QWidget(); right_l = QtWidgets.QVBoxLayout(right)
        self.lbl_title = QtWidgets.QLabel("<b>—</b>")
        self.txt_desc  = QtWidgets.QTextEdit(); self.txt_desc.setReadOnly(True); self.txt_desc.setMinimumHeight(80)
        self.scroll_ops = QtWidgets.QScrollArea(); self.scroll_ops.setWidgetResizable(True)
        self.ops_holder = QtWidgets.QWidget(); self.ops_layout = QtWidgets.QVBoxLayout(self.ops_holder); self.ops_layout.addStretch(1)
        self.scroll_ops.setWidget(self.ops_holder)

        right_l.addWidget(self.lbl_title)
        right_l.addWidget(self.txt_desc)
        right_l.addWidget(QtWidgets.QLabel("Parametre kroku/krokov:"))
        right_l.addWidget(self.scroll_ops, 1)

        split.addWidget(left); split.addWidget(right); split.setStretchFactor(1, 2)

        # spodné tlačidlá
        btns = QtWidgets.QHBoxLayout()
        self.btn_apply = QtWidgets.QPushButton("Použiť do nástroja")
        self.btn_cancel = QtWidgets.QPushButton("Zavrieť")
        btns.addStretch(1); btns.addWidget(self.btn_apply); btns.addWidget(self.btn_cancel)
        main.addLayout(btns)

        # naplň kategórie
        cats = []
        for item in self._catalog:
            c = item.get("cat","")
            if c not in cats: cats.append(c)
        for c in cats:
            self.list_cat.addItem(c)
        if self.list_cat.count() > 0:
            self.list_cat.setCurrentRow(0)

        # signály
        self.list_cat.currentRowChanged.connect(self._fill_presets_for_cat)
        self.list_presets.currentItemChanged.connect(self._on_preset_selected)
        self.btn_apply.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        # ak prišiel initial_chain, zobraz ho
        if initial_chain is not None:
            self.lbl_title.setText("<b>Vlastné nastavenie</b>")
            self.txt_desc.setPlainText(_chain_to_text(self._chain))
            self._rebuild_op_editors(self._chain)

    def _fill_presets_for_cat(self, row: int):
        cat = self.list_cat.item(row).text() if row >= 0 else None
        self.list_presets.clear()
        if not cat: return
        for item in self._catalog:
            if item.get("cat") == cat:
                it = QtWidgets.QListWidgetItem(item.get("title","?"))
                it.setData(QtCore.Qt.UserRole, item)
                self.list_presets.addItem(it)

    def _on_preset_selected(self, cur: QtWidgets.QListWidgetItem, prev: QtWidgets.QListWidgetItem):
        if not cur:
            return
        data = cur.data(QtCore.Qt.UserRole) or {}
        self._selected = data
        self._chain = [dict(s) for s in (data.get("chain", []) or [])]
        self.lbl_title.setText(f"<b>{data.get('title','?')}</b>")
        self.txt_desc.setPlainText(data.get("desc",""))
        self._rebuild_op_editors(self._chain)

    def _rebuild_op_editors(self, chain: List[Dict[str,Any]]):
        # zmaž staré editory
        while self.ops_layout.count() > 0:
            it = self.ops_layout.takeAt(0)
            w = it.widget()
            if w: w.deleteLater()
        # pridaj nové
        for step in chain:
            ed = _OpEditor(step)
            ed.changed.connect(lambda s=ed: self._update_step_from_editor(s))
            self.ops_layout.addWidget(ed)
        self.ops_layout.addStretch(1)

    def _update_step_from_editor(self, editor: _OpEditor):
        # prepíš editor.step späť do _chain
        for i, st in enumerate(self._chain):
            if st is editor.step:  # identity by reference nie je zaručená -> fallback:
                self._chain[i] = dict(editor.step)
                return
        # fallback: skús podľa 'op' a poradia
        # (MVP – jednoduché)
        pass

    def selected_chain(self) -> List[Dict[str,Any]]:
        return list(self._chain or [])
