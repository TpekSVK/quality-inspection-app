# app/widgets/preproc_catalog.py
from typing import List, Dict, Any
from PyQt5 import QtWidgets, QtCore

DEFAULT_PREPROC = [
    {"cat":"Žiadne", "title":"Bez predspracovania", "desc":"Vypnuté.", "chain":[]},

    {"cat":"Osvetlenie", "title":"Homomorphic (σ=30, gain=1.2)", "desc":"Vyrovná nerovné osvetlenie (log - log blur).",
     "chain":[{"op":"homo","sigma":30.0,"gain":1.2}]},
    {"cat":"Osvetlenie", "title":"Retinex SSR (σ=25)", "desc":"Jednoduchý Retinex – detaily v tieni.",
     "chain":[{"op":"retinex","sigma":25.0}]},
    {"cat":"Kontrast", "title":"CLAHE 2.0 (8×8)", "desc":"Lokálne vyrovnanie kontrastu – vytiahne jemné detaily.",
     "chain":[{"op":"clahe","clip":2.0,"tile":8}]},
    {"cat":"Kontrast", "title":"Equalize Hist", "desc":"Klasická histogramová equalizácia (celý ROI).",
     "chain":[{"op":"equalize"}]},

    {"cat":"Hrany", "title":"Morph. gradient k=5", "desc":"Zvýrazní hrany (dilate − erode).",
     "chain":[{"op":"morphgrad","k":5}]},
    {"cat":"Hrany", "title":"LoG (k=7)", "desc":"Laplacian of Gaussian – čisté hrany.",
     "chain":[{"op":"log","k":7}]},
    {"cat":"Hrany", "title":"Unsharp 1.2 / r=3", "desc":"Doostrenie pred edge detekciou.",
     "chain":[{"op":"unsharp","amount":1.2,"radius":3}]},

    {"cat":"Šum", "title":"Median 3×3", "desc":"Odstráni soľ-a-korenie šum.",
     "chain":[{"op":"median","k":3}]},
    {"cat":"Šum", "title":"Guided r=7 eps=1e-3", "desc":"Hrany zachovávajúce vyhladenie (fallback na bilateral).",
     "chain":[{"op":"guided","r":7,"eps":1e-3}]},
    {"cat":"Šum", "title":"Fast NLM h=10", "desc":"Silný odšum (len menšie ROI).",
     "chain":[{"op":"nlm","h":10.0}]},

    {"cat":"Pozadie", "title":"Top-hat 15", "desc":"Odstráni hladké pozadie, nechá malé svetlé vady.",
     "chain":[{"op":"tophat","k":15}]},
    {"cat":"Pozadie", "title":"Rolling-ball r=25", "desc":"Otvorenie ako odhad pozadia, potom odčítané.",
     "chain":[{"op":"rollball","r":25}]},

    {"cat":"Prahovanie", "title":"Sauvola win=25, k=0.2", "desc":"Adaptívna binarizácia (textúra/OCR).",
     "chain":[{"op":"sauvola","win":25,"k":0.2}]},

    {"cat":"Textúra/Škrabance", "title":"Gabor bank (0,45,90,135; f=0.15)", "desc":"Zvýrazní ryhy v daných smeroch.",
     "chain":[{"op":"gabor","angles":[0,45,90,135],"freq":0.15,"ksize":21,"sigma":4.0,"gamma":0.5}]},

    {"cat":"Normalizácia", "title":"Z-score", "desc":"Zjednotí jas/kontrast naprieč dávkami.",
     "chain":[{"op":"zscore"}]},
    {"cat":"Normalizácia", "title":"Clip 5–95%", "desc":"Oreže outliery a rescalne rozsah.",
     "chain":[{"op":"clip","lo":5.0,"hi":95.0}]},

    {"cat":"Kombinácia", "title":"Median + CLAHE", "desc":"Najprv odšum, potom lokálny kontrast.",
     "chain":[{"op":"median","k":3},{"op":"clahe","clip":2.0,"tile":8}]}
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
        # DRŽÍME REFERENCIU (nie kópiu), nech sa zmeny prejavia v chain-e
        self.step = step
        form = QtWidgets.QFormLayout(self)
        self.widgets = {}

        def add_spin(name, key, vmin, vmax, stepv=1, dec=False, val=None):
            if dec:
                w = QtWidgets.QDoubleSpinBox(); w.setRange(vmin, vmax); w.setSingleStep(stepv)
                w.setValue(float(self.step.get(key, val if val is not None else 0.0)))
            else:
                w = QtWidgets.QSpinBox(); w.setRange(vmin, vmax); w.setSingleStep(stepv)
                w.setValue(int(self.step.get(key, val if val is not None else 0)))
            w.valueChanged.connect(self._on_changed)
            self.widgets[key] = w
            form.addRow(name, w)

        def add_line(name, key, placeholder=""):
            w = QtWidgets.QLineEdit()
            w.setText(str(self.step.get(key, "")))
            w.setPlaceholderText(placeholder)
            w.textChanged.connect(self._on_changed)
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
            add_spin("clip", "clip", 0.1, 40.0, 0.1, dec=True, val=2.0)
            add_spin("tile", "tile", 2, 64, 1, dec=False, val=8)
        elif op in ("tophat","blackhat","morphgrad","log"):
            add_spin("K (px, nepárne)", "k", 3, 99, 2, dec=False, val=15)
        elif op == "unsharp":
            add_spin("amount", "amount", 0.0, 5.0, 0.1, dec=True, val=1.0)
            add_spin("radius", "radius", 1, 51, 2, dec=False, val=3)
        elif op == "normalize":
            add_spin("alpha", "alpha", 0.0, 255.0, 1.0, dec=True, val=0.0)
            add_spin("beta",  "beta",  0.0, 255.0, 1.0, dec=True, val=255.0)
        elif op == "homo":
            add_spin("sigma", "sigma", 1.0, 200.0, 1.0, dec=True, val=30.0)
            add_spin("gain",  "gain",  0.1, 5.0,   0.1, dec=True, val=1.2)
        elif op == "retinex":
            add_spin("sigma", "sigma", 1.0, 200.0, 1.0, dec=True, val=25.0)
        elif op == "guided":
            add_spin("r (radius)", "r", 1, 64, 1, dec=False, val=7)
            add_spin("eps", "eps", 1e-6, 1e-1, 1e-3, dec=True, val=1e-3)
        elif op == "nlm":
            add_spin("h", "h", 1.0, 30.0, 0.5, dec=True, val=10.0)
        elif op == "rollball":
            add_spin("r (px, nepárne)", "r", 3, 199, 2, dec=False, val=25)
        elif op == "sauvola":
            add_spin("win (px, nepárne)", "win", 3, 199, 2, dec=False, val=25)
            add_spin("k", "k", 0.01, 0.5, 0.01, dec=True, val=0.2)
        elif op == "clip":
            add_spin("lo [%]", "lo", 0.0, 99.0, 1.0, dec=True, val=5.0)
            add_spin("hi [%]", "hi", 1.0, 100.0, 1.0, dec=True, val=95.0)
        elif op == "gabor":
            add_line("angles (°)", "angles", "napr. 0,45,90,135")
            add_spin("freq (cykly/px)", "freq", 0.01, 0.5, 0.01, dec=True, val=0.15)
            add_spin("ksize", "ksize", 7, 101, 2, dec=False, val=21)
            add_spin("sigma", "sigma", 0.5, 20.0, 0.5, dec=True, val=4.0)
            add_spin("gamma", "gamma", 0.1, 2.0, 0.1, dec=True, val=0.5)
        else:
            lab = QtWidgets.QLabel("Tento op nemá editovateľné parametre.")
            form.addRow(lab)

    def _on_changed(self, *_):
        # uloží hodnoty späť
        for k, w in self.widgets.items():
            if isinstance(w, QtWidgets.QDoubleSpinBox):
                self.step[k] = float(w.value())
            elif isinstance(w, QtWidgets.QSpinBox):
                self.step[k] = int(w.value())
            elif isinstance(w, QtWidgets.QLineEdit):
                val = w.text().strip()
                if k == "angles":
                    try:
                        self.step[k] = [int(s) for s in val.split(",") if s.strip()!=""]
                    except Exception:
                        self.step[k] = val
                else:
                    self.step[k] = val
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
        self._chain = [dict(s) for s in (initial_chain or [])]

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
        self._update_summary()


    def _rebuild_op_editors(self, chain: List[Dict[str,Any]]):
        # zmaž staré editory
        while self.ops_layout.count() > 0:
            it = self.ops_layout.takeAt(0)
            w = it.widget()
            if w: w.deleteLater()
        # pridaj nové
        for step in chain:
            ed = _OpEditor(step)
            # keď sa zmení parameter v editore, reťazec je už prepísaný (referencia),
            # stačí obnoviť textový sumár
            ed.changed.connect(self._update_summary)
            self.ops_layout.addWidget(ed)
        self.ops_layout.addStretch(1)


    def _update_summary(self):
        self.txt_desc.setPlainText(_chain_to_text(self._chain))


    def selected_chain(self) -> List[Dict[str,Any]]:
        # Builder si uloží čistú kópiu
        return [dict(s) for s in (self._chain or [])]

