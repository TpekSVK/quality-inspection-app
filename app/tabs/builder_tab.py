# app/tabs/builder_tab.py
from PyQt5 import QtWidgets, QtCore
from pathlib import Path
import numpy as np
import cv2 as cv

from storage.recipe_store_json import RecipeStoreJSON
from app.widgets.roi_drawer import ROIDrawer

def _mask_label(idx: int) -> str:
    return f"Maska {idx+1}"

HELP_TEXTS = {
    "thresh": (
        "Citlivosť – prahovanie\n"
        "• Určuje, aká veľká zmena od referencie sa počíta ako vada.\n"
        "• Nižšie = citlivejšie (viac poplachov), vyššie = menej citlivé.\n"
        "• Typicky 35–45 (mono/NIR). Ak šumí, skús 45–60."
    ),
    "morph": (
        "Čistenie šumu – iterácie (morfologické OPEN)\n"
        "• Odstraňuje malé bodky šumu, vyhladí masku vád.\n"
        "• 0–2 býva dosť; 1 je dobrý štart."
    ),
    "blob": (
        "Min. plocha vady [px²]\n"
        "• Ignoruje drobné fliačky/šum pod touto plochou.\n"
        "• Pre ‚stredné a väčšie‘ vady skús 150–500 px² (podľa px/mm)."
    ),
    "measure": (
        "Metóda merania\n"
        "• Plocha vád (px²): súčet plôch všetkých nájdených vád.\n"
        "• Počet vád: len počítame kusy."
    ),
    "lsl": (
        "Spodná hranica (LSL)\n"
        "• Väčšinou sa nepoužíva pre plochu vád (nechaj None)."
    ),
    "usl": (
        "Horná hranica (USL)\n"
        "• Nad touto hodnotou je diel NOK.\n"
        "• Nastav automaticky cez Auto-teach z OK snímok."
    ),
    "masks": (
        "Masky (fialové)\n"
        "• Oblasti, ktoré IGNORUJEME pri kontrole (držáky, okraje...).\n"
        "• Môže ich byť viac; ťahaj rohy/okraje na jemné doladenie."
    ),
    "roi": (
        "ROI (modrá)\n"
        "• Oblasť, v ktorej nástroj meria. Ťahaj rohy/okraje pre resize,\n"
        "  ťahaj dovnútra pre posun."
    ),
    "preset": (
        "Predvoľby (presety)\n"
        "• Rýchle nastavenie parametrov pre typ povrchu / požadovanú citlivosť."
    ),
}

PRESETS = {
    "Plast (matný)":        {"thresh": 35, "morph": 1, "blob": 120, "measure":"area"},
    "Plast (lesklý)":       {"thresh": 45, "morph": 1, "blob": 200, "measure":"area"},
    "Kov (matný)":          {"thresh": 40, "morph": 1, "blob": 150, "measure":"area"},
    "Kov (lesklý)":         {"thresh": 55, "morph": 2, "blob": 300, "measure":"area"},
    "Guma / NIR":           {"thresh": 35, "morph": 1, "blob": 180, "measure":"area"},
    "Hrubé vady 1mm+":      {"thresh": 50, "morph": 1, "blob": 500, "measure":"area"},
    "Citlivé (laboratórne)":{"thresh": 25, "morph": 0, "blob": 60,  "measure":"area"},
}

class BuilderTab(QtWidgets.QWidget):
    """
    – Živá nápoveda: ukazuje sa pod tlačidlom „Použiť zmeny…“ podľa toho,
      ktorého poľa sa dotkneš.
    – Úchyty: ROI aj masky vieš chytiť za rohy/okraje a meniť.
    – Masky = ignorované oblasti (fialové), viac kusov naraz.
    """
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.store = RecipeStoreJSON()
        self.recipe = {"tools":[]}
        self.current_tool_idx = None
        self.ref_img = None
        self._build()
        self.load_recipe()

    def _build(self):
        layout = QtWidgets.QHBoxLayout(self)

        # ĽAVO
        left = QtWidgets.QVBoxLayout()
        hl = QtWidgets.QHBoxLayout()
        self.edit_recipe = QtWidgets.QLineEdit(self.state.current_recipe or "FORMA_X_PRODUCT_Y")
        btn_load = QtWidgets.QPushButton("Načítať")
        btn_save = QtWidgets.QPushButton("Uložiť verziu")
        hl.addWidget(self.edit_recipe); hl.addWidget(btn_load); hl.addWidget(btn_save)

        self.list_tools = QtWidgets.QListWidget()
        self.list_tools.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        cat = QtWidgets.QHBoxLayout()
        self.cmb_new = QtWidgets.QComboBox()
        self.cmb_new.addItems(["Porovnanie s referenciou", "Prítomnosť/Absencia", "YOLO v ROI"])
        self.btn_add = QtWidgets.QPushButton("Pridať nástroj")
        self.btn_del = QtWidgets.QPushButton("Odstrániť nástroj")
        cat.addWidget(self.cmb_new); cat.addWidget(self.btn_add); cat.addWidget(self.btn_del)

        left.addLayout(hl)
        left.addWidget(QtWidgets.QLabel("Nástroje v recepte:"))
        left.addWidget(self.list_tools, 1)
        left.addLayout(cat)

        # STRED
        mid = QtWidgets.QVBoxLayout()
        self.roi_view = ROIDrawer()
        mode_bar = QtWidgets.QHBoxLayout()
        self.btn_mode_roi = QtWidgets.QRadioButton("Režim ROI (modrá)")
        self.btn_mode_mask = QtWidgets.QRadioButton("Režim maska – ignorovať (fialová)")
        self.btn_mode_roi.setChecked(True)
        mode_bar.addWidget(self.btn_mode_roi); mode_bar.addWidget(self.btn_mode_mask)

        self.btn_use_roi = QtWidgets.QPushButton("Použiť aktuálne nakreslené ROI")
        mid.addWidget(self.roi_view, 1)
        mid.addLayout(mode_bar)
        mid.addWidget(self.btn_use_roi)

        mid.addWidget(QtWidgets.QLabel("Masky (ignorované oblasti):"))
        self.list_masks = QtWidgets.QListWidget()
        self.list_masks.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        mask_bar = QtWidgets.QHBoxLayout()
        self.btn_add_mask = QtWidgets.QPushButton("Pridať masku z kreslenia")
        self.btn_del_mask = QtWidgets.QPushButton("Odstrániť vybranú masku")
        self.btn_clear_masks = QtWidgets.QPushButton("Vymazať všetky masky")
        mask_bar.addWidget(self.btn_add_mask); mask_bar.addWidget(self.btn_del_mask); mask_bar.addWidget(self.btn_clear_masks)
        mid.addWidget(self.list_masks, 1)
        mid.addLayout(mask_bar)

        # PRAVO
        right = QtWidgets.QFormLayout()
        self.lbl_type = QtWidgets.QLabel("-")
        self.edit_name = QtWidgets.QLineEdit("Kontrola A")

        # Presety
        self.cmb_preset = QtWidgets.QComboBox()
        self.cmb_preset.addItems(list(PRESETS.keys()))
        self.btn_preset = QtWidgets.QPushButton("Použiť predvoľbu")

        # Parametre (SLK)
        self.spin_thresh = QtWidgets.QSpinBox(); self.spin_thresh.setRange(0,255); self.spin_thresh.setValue(35); self.spin_thresh.setObjectName("thresh")
        self.spin_morph = QtWidgets.QSpinBox(); self.spin_morph.setRange(0,10);  self.spin_morph.setValue(1);  self.spin_morph.setObjectName("morph")
        self.spin_blob  = QtWidgets.QSpinBox(); self.spin_blob.setRange(0,100000); self.spin_blob.setValue(120); self.spin_blob.setObjectName("blob")
        self.cmb_measure = QtWidgets.QComboBox(); self.cmb_measure.addItems(["Plocha vád (px²)", "Počet vád"]); self.cmb_measure.setObjectName("measure")

        self.dbl_lsl = QtWidgets.QDoubleSpinBox(); self.dbl_lsl.setRange(-1e9,1e9); self.dbl_lsl.setDecimals(3); self.dbl_lsl.setSpecialValueText("None"); self.dbl_lsl.setObjectName("lsl")
        self.dbl_usl = QtWidgets.QDoubleSpinBox(); self.dbl_usl.setRange(-1e9,1e9); self.dbl_usl.setDecimals(3); self.dbl_usl.setValue(200.0); self.dbl_usl.setObjectName("usl")
        self.edit_units = QtWidgets.QLineEdit("px²")

        self.spin_fpr = QtWidgets.QDoubleSpinBox(); self.spin_fpr.setRange(0.0001,0.1); self.spin_fpr.setDecimals(4); self.spin_fpr.setValue(0.003)
        self.btn_autoteach = QtWidgets.QPushButton("Auto-teach horná hranica (USL) z OK snímok")

        self.btn_apply = QtWidgets.QPushButton("Použiť zmeny do nástroja")

        # Kontextová nápoveda (sem sa zobrazuje help)
        self.help_box = QtWidgets.QTextEdit()
        self.help_box.setReadOnly(True)
        self.help_box.setMinimumHeight(120)
        self.help_box.setStyleSheet("QTextEdit{background:#111; color:#ddd; border-radius:8px; padding:8px;}")

        right.addRow("<b>Typ nástroja</b>", self.lbl_type)
        right.addRow("Názov (krátko)", self.edit_name)
        right.addRow(QtWidgets.QLabel("<hr>"))
        right.addRow("Predvoľba", self.cmb_preset)
        right.addRow("", self.btn_preset)
        right.addRow(QtWidgets.QLabel("<hr>"))
        right.addRow("Citlivosť – prahovanie", self.spin_thresh)
        right.addRow("Čistenie šumu – iterácie", self.spin_morph)
        right.addRow("Min. plocha vady [px²]", self.spin_blob)
        right.addRow("Metóda merania", self.cmb_measure)
        right.addRow(QtWidgets.QLabel("<hr>"))
        right.addRow("Spodná hranica (LSL)", self.dbl_lsl)
        right.addRow("Horná hranica (USL)", self.dbl_usl)
        right.addRow("Jednotky", self.edit_units)
        right.addRow(QtWidgets.QLabel("<hr>"))
        right.addRow("Cieľová FPR", self.spin_fpr)
        right.addRow("", self.btn_autoteach)
        right.addRow(QtWidgets.QLabel("<hr>"))
        right.addRow("", self.btn_apply)
        right.addRow("Nápoveda", self.help_box)

        layout.addLayout(left, 1)
        layout.addLayout(mid, 1)
        layout.addLayout(right, 1)

        # Signály
        btn_load.clicked.connect(self.load_recipe)
        btn_save.clicked.connect(self.save_recipe)
        self.list_tools.currentRowChanged.connect(self._on_tool_selected)
        self.btn_add.clicked.connect(self.add_tool)
        self.btn_del.clicked.connect(self.del_tool)
        self.btn_mode_roi.toggled.connect(self._on_mode_roi)
        self.btn_use_roi.clicked.connect(self.use_drawn_roi)
        self.btn_add_mask.clicked.connect(self.add_mask_from_drawn)
        self.btn_del_mask.clicked.connect(self.delete_selected_mask)
        self.btn_clear_masks.clicked.connect(self.clear_masks)
        self.list_masks.itemSelectionChanged.connect(self._on_mask_selected)
        self.roi_view.maskAdded.connect(lambda *_: self._refresh_mask_list())
        self.btn_preset.clicked.connect(self.apply_preset)
        self.btn_apply.clicked.connect(self.apply_changes)
        self.btn_autoteach.clicked.connect(self.run_autoteach)

        # Kontextová nápoveda – sleduj focus
        for w in (self.spin_thresh, self.spin_morph, self.spin_blob, self.cmb_measure,
                  self.dbl_lsl, self.dbl_usl, self.cmb_preset):
            w.installEventFilter(self)

    # ---- Event filter pre nápovedu ----
    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.FocusIn:
            name = obj.objectName()
            key = None
            if obj is self.cmb_preset: key = "preset"
            elif name in ("thresh","morph","blob","measure","lsl","usl"):
                key = name
            if key and key in HELP_TEXTS:
                self.help_box.setPlainText(HELP_TEXTS[key])
        return super().eventFilter(obj, ev)

    # ------------- Dáta -------------
    def load_recipe(self):
        name = self.edit_recipe.text().strip()
        try:
            self.recipe = self.store.load(name)
        except Exception:
            self.recipe = {"meta":{"name":name},"reference_image":None,"tools":[]}
        self.state.current_recipe = name
        self._refresh_tool_list()
        self._load_ref_image()
        if self.list_tools.count() > 0:
            self.list_tools.setCurrentRow(0)

    def save_recipe(self):
        name = self.edit_recipe.text().strip()
        self.store.save_version(name, self.recipe)
        QtWidgets.QMessageBox.information(self, "OK", f"Recept {name} uložený.")
        try:
            self.state.build_from_recipe(name)
        except Exception:
            pass

    def _load_ref_image(self):
        ref_path = self.recipe.get("reference_image", None)
        if ref_path and Path(ref_path).exists():
            img = cv.imread(ref_path, cv.IMREAD_GRAYSCALE)
            self.ref_img = img
            self.roi_view.set_ndarray(img)
        else:
            self.ref_img = None
            self.roi_view.setText("— (referencia nie je nastavená)")

    def _refresh_tool_list(self):
        self.list_tools.clear()
        for t in self.recipe.get("tools", []):
            typ = t.get("type","-")
            sk_typ = {"diff_from_ref":"Porovnanie s referenciou",
                      "presence_absence":"Prítomnosť/Absencia",
                      "yolo_roi":"YOLO v ROI"}.get(typ, typ)
            nm = t.get("name","Kontrola")
            usl = t.get("usl", None)
            self.list_tools.addItem(f"{sk_typ}  |  {nm}  |  USL={usl}")

    # ------------- UI handlers -------------
    def _on_tool_selected(self, row: int):
        self.current_tool_idx = row
        if row < 0:
            self._clear_form(); 
            return
        t = self.recipe.get("tools", [])[row]
        typ = t.get("type","-")
        sk_typ = {"diff_from_ref":"Porovnanie s referenciou",
                  "presence_absence":"Prítomnosť/Absencia",
                  "yolo_roi":"YOLO v ROI"}.get(typ, typ)
        self.lbl_type.setText(sk_typ)
        self.edit_name.setText(t.get("name","Kontrola A"))

        x,y,w,h = t.get("roi_xywh",[0,0,200,200])
        self.roi_view.set_roi(x,y,w,h)

        params = t.get("params",{})
        masks = params.get("mask_rects", []) or []
        self.roi_view.set_masks(masks)
        self._refresh_mask_list()

        self.dbl_lsl.setValue(t.get("lsl", 0.0) if t.get("lsl") is not None else 0.0)
        self.dbl_usl.setValue(t.get("usl", 200.0) if t.get("usl") is not None else 200.0)
        self.edit_units.setText(t.get("units","px²"))

        self.spin_thresh.setValue(int(params.get("thresh",35)))
        self.spin_morph.setValue(int(params.get("morph_open",1)))
        self.spin_blob.setValue(int(params.get("min_blob_area",120)))
        self.cmb_measure.setCurrentText("Plocha vád (px²)" if params.get("measure","area")=="area" else "Počet vád")

        is_diff = (typ=="diff_from_ref")
        for w in (self.spin_thresh, self.spin_morph, self.spin_blob, self.cmb_measure,
                  self.btn_add_mask, self.btn_del_mask, self.btn_clear_masks,
                  self.cmb_preset, self.btn_preset):
            w.setEnabled(is_diff)

    def _on_mode_roi(self, checked: bool):
        self.roi_view.set_mode("roi" if checked else "mask")
        self.help_box.setPlainText(HELP_TEXTS["roi" if checked else "masks"])

    def _on_mask_selected(self):
        idx = self.list_masks.currentRow()
        self.roi_view.set_active_mask_index(idx)

    def use_drawn_roi(self):
        if not self.roi_view._roi:
            QtWidgets.QMessageBox.information(self, "ROI", "Nakresli ROI v režime ROI.")
            return
        QtWidgets.QMessageBox.information(self, "ROI", "ROI nastavené. Klikni „Použiť zmeny do nástroja“ a potom „Uložiť verziu“.")

    def add_mask_from_drawn(self):
        rect = getattr(self.roi_view, "_temp_rect", None) or self.roi_view._roi
        if not rect:
            QtWidgets.QMessageBox.information(self, "Maska", "Nakresli obdĺžnik v režime MASKA (fialová).")
            return
        x,y,w,h = rect
        self.roi_view.add_mask_rect(x,y,w,h)
        self._refresh_mask_list()

    def delete_selected_mask(self):
        row = self.list_masks.currentRow()
        if row < 0: return
        masks = self.roi_view.masks()
        del masks[row]
        self.roi_view.set_masks(masks)
        self._refresh_mask_list()

    def clear_masks(self):
        self.roi_view.clear_masks()
        self._refresh_mask_list()

    def _refresh_mask_list(self):
        self.list_masks.clear()
        for i,_ in enumerate(self.roi_view.masks()):
            self.list_masks.addItem(_mask_label(i))

    def apply_preset(self):
        name = self.cmb_preset.currentText()
        p = PRESETS.get(name)
        if not p: return
        self.spin_thresh.setValue(p["thresh"])
        self.spin_morph.setValue(p["morph"])
        self.spin_blob.setValue(p["blob"])
        self.cmb_measure.setCurrentText("Plocha vád (px²)" if p["measure"]=="area" else "Počet vád")
        self.help_box.setPlainText(HELP_TEXTS["preset"])

    def add_tool(self):
        label = self.cmb_new.currentText()
        typ_map = {
            "Porovnanie s referenciou": "diff_from_ref",
            "Prítomnosť/Absencia": "presence_absence",
            "YOLO v ROI": "yolo_roi"
        }
        typ = typ_map.get(label, "diff_from_ref")
        new = {
            "type": typ,
            "name": f"Kontrola {chr(65 + len(self.recipe.get('tools',[])))}",
            "roi_xywh": [0,0,200,200],
            "params": {},
            "lsl": None,
            "usl": None,
            "units": "px²" if typ=="diff_from_ref" else "ks"
        }
        if typ == "diff_from_ref":
            new["params"] = {"blur":3, "thresh":35, "morph_open":1, "min_blob_area":120, "measure":"area", "mask_rects":[]}
        self.recipe.setdefault("tools", []).append(new)
        self._refresh_tool_list()
        self.list_tools.setCurrentRow(self.list_tools.count()-1)

    def del_tool(self):
        idx = self.list_tools.currentRow()
        if idx < 0: return
        del self.recipe["tools"][idx]
        self._refresh_tool_list()
        self.current_tool_idx = None
        self._clear_form()

    def _clear_form(self):
        self.lbl_type.setText("-")
        self.edit_name.setText("Kontrola A")
        self.roi_view.clear_roi()
        self.roi_view.clear_masks()
        self._refresh_mask_list()
        self.dbl_lsl.setValue(0.0); self.dbl_usl.setValue(200.0); self.edit_units.setText("px²")
        self.spin_thresh.setValue(35); self.spin_morph.setValue(1); self.spin_blob.setValue(120)
        self.cmb_measure.setCurrentText("Plocha vád (px²)")
        self.help_box.clear()

    def apply_changes(self):
        idx = self.current_tool_idx
        if idx is None or idx < 0: return
        t = self.recipe["tools"][idx]
        t["name"] = self.edit_name.text().strip() or f"Kontrola {idx+1}"
        if self.roi_view._roi:
            x,y,w,h = self.roi_view._roi
            t["roi_xywh"] = [int(x),int(y),int(w),int(h)]
        t["lsl"] = None if self.dbl_lsl.specialValueText()=="None" else float(self.dbl_lsl.value())
        t["usl"] = float(self.dbl_usl.value())
        t["units"] = self.edit_units.text().strip() or ("px²" if t.get("type")=="diff_from_ref" else "ks")
        if t.get("type") == "diff_from_ref":
            p = t.setdefault("params",{})
            p["thresh"] = int(self.spin_thresh.value())
            p["morph_open"] = int(self.spin_morph.value())
            p["min_blob_area"] = int(self.spin_blob.value())
            p["measure"] = "area" if self.cmb_measure.currentText().startswith("Plocha") else "count"
            p["mask_rects"] = [[int(a) for a in r] for r in self.roi_view.masks()]
        self._refresh_tool_list()
        QtWidgets.QMessageBox.information(self, "OK", "Zmeny aplikované. Nezabudni „Uložiť verziu“.")

    def run_autoteach(self):
        name = self.edit_recipe.text().strip()
        ok_dir = Path("datasets")/name/"ok"
        if not ok_dir.exists():
            QtWidgets.QMessageBox.warning(self, "Auto-teach", f"Chýbajú OK snímky v {ok_dir}")
            return
        idx = self.current_tool_idx
        if idx is None or idx < 0:
            QtWidgets.QMessageBox.warning(self, "Auto-teach", "Vyber najprv nástroj.")
            return
        ref_path = self.recipe.get("reference_image", None)
        if not ref_path or not Path(ref_path).exists():
            QtWidgets.QMessageBox.warning(self, "Auto-teach", "Chýba referenčný obrázok v recepte.")
            return
        ref = cv.imread(ref_path, cv.IMREAD_GRAYSCALE)
        t = self.recipe["tools"][idx]
        from core.tools.diff_from_ref import DiffFromRefTool
        tool = DiffFromRefTool(
            name=t.get("name","Kontrola"),
            roi_xywh=tuple(t.get("roi_xywh",[0,0,200,200])),
            params=t.get("params",{}),
            lsl=t.get("lsl"), usl=t.get("usl"),
            units=t.get("units","px²")
        )
        vals=[]
        imgs = sorted(list((ok_dir).glob("*.png")) + list((ok_dir).glob("*.jpg")) + list((ok_dir).glob("*.bmp")))
        for pth in imgs:
            cur = cv.imread(str(pth), cv.IMREAD_GRAYSCALE)
            if cur is None: continue
            r = tool.run(ref, cur, fixture_transform=None)
            vals.append(float(r.measured))
        if not vals:
            QtWidgets.QMessageBox.warning(self, "Auto-teach", "Nenašiel som použiteľné OK snímky.")
            return
        import numpy as np
        vals = np.array(vals, dtype=float)
        perc = 100.0 * (1.0 - float(self.spin_fpr.value()))
        usl = float(np.percentile(vals, perc))
        self.dbl_usl.setValue(usl)
        QtWidgets.QMessageBox.information(self, "Auto-teach", f"Navrhované USL = {usl:.2f}. Klikni „Použiť zmeny“ a potom „Uložiť verziu“.")
