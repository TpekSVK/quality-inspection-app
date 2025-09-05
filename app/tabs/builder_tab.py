# app/tabs/builder_tab.py
from PyQt5 import QtWidgets, QtCore, QtGui
from pathlib import Path
import numpy as np
import cv2 as cv

from storage.recipe_store_json import RecipeStoreJSON
from app.widgets.roi_drawer import ROIDrawer
from app.widgets.tools_catalog import ToolCatalogDialog
try:
    from core.tools.presence_absence import PresenceAbsenceTool
except Exception:
    PresenceAbsenceTool = None
try:
    from core.tools.yolo_roi import YoloRoiTool
except Exception:
    YoloRoiTool = None
try:
    from core.tools.diff_from_ref import DiffFromRefTool
except Exception:
    DiffFromRefTool = None

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
        "• Nastav automaticky cez Auto-teach z OK snímok, alebo OK+NOK."
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
    – Auto-teach: z OK (percentil) alebo OK+NOK (optimálny prah).
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
        self._update_mask_buttons()

    # ---------- Pomocné ----------
    def _active_tool_type(self) -> str:
        idx = self.current_tool_idx
        if idx is None or idx < 0:
            return ""
        try:
            return (self.recipe.get("tools", [])[idx] or {}).get("type","") or ""
        except Exception:
            return ""

    def _tool_allows_masks(self) -> bool:
        typ = (self._active_tool_type() or "").lower()
        # masky majú zmysel pre tieto typy nástrojov:
        return typ in {"diff_from_ref", "presence_absence", "yolo_roi"}

    def _update_mask_buttons(self):
        allow = self._tool_allows_masks()
        # stav zoznamu masiek a výber
        has_masks = False
        has_sel = False
        try:
            has_masks = len(self.roi_view.masks()) > 0
        except Exception:
            pass
        try:
            has_sel = self.list_masks.currentRow() >= 0
        except Exception:
            pass

        # enably
        if hasattr(self, "btn_add_mask"):
            self.btn_add_mask.setEnabled(allow)
        if hasattr(self, "btn_del_mask"):
            self.btn_del_mask.setEnabled(allow and has_masks and has_sel)
        if hasattr(self, "btn_clear_masks"):
            self.btn_clear_masks.setEnabled(allow and has_masks)

        # režimové tlačidlá
        if hasattr(self, "btn_mode_mask"):
            self.btn_mode_mask.setEnabled(allow)
        if hasattr(self, "btn_mode_roi"):
            self.btn_mode_roi.setEnabled(True)  # ROI má zmysel vždy

    # ---------- UI ----------
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
        self.btn_catalog = QtWidgets.QPushButton("Katalóg nástrojov…")
        self.btn_del = QtWidgets.QPushButton("Odstrániť nástroj")
        cat.addWidget(self.btn_catalog); cat.addWidget(self.btn_del)

        left.addLayout(hl)
        left.addWidget(QtWidgets.QLabel("Nástroje v recepte:"))
        left.addWidget(self.list_tools, 1)
        left.addLayout(cat)


        # STRED
        mid = QtWidgets.QVBoxLayout()
        self.roi_view = ROIDrawer()
        mode_bar = QtWidgets.QHBoxLayout()
        self.btn_mode_roi = QtWidgets.QRadioButton("ROI (modrá)")
        self.btn_mode_mask = QtWidgets.QRadioButton("Maska (fialová)")
        self.btn_mode_line = QtWidgets.QRadioButton("Čiara")
        self.btn_mode_circle = QtWidgets.QRadioButton("Kružnica")
        self.btn_mode_poly = QtWidgets.QRadioButton("Krivka")

        self._set_mode_icons()


        self.btn_mode_roi.setChecked(True)


        for b in (self.btn_mode_roi, self.btn_mode_mask, self.btn_mode_line, self.btn_mode_circle, self.btn_mode_poly):
            mode_bar.addWidget(b)
        mode_bar.addStretch(1)



        # šírka profilu (pre line/circle/polyline)
        self.spin_width = QtWidgets.QSpinBox()
        self.spin_width.setRange(1, 50)
        self.spin_width.setValue(3)
        self.lbl_width = QtWidgets.QLabel("Šírka profilu:")
        mode_bar.addWidget(self.lbl_width)
        mode_bar.addWidget(self.spin_width)



        self.btn_mode_roi.setToolTip("Kresli a upravuj meraciu oblasť (ROI).")
        self.btn_mode_mask.setToolTip("Kresli ignorované oblasti – čo sa nemá počítať.")
        self.btn_mode_line.setToolTip("Nakresli úsečku: klik začiatok → ťahaj → pusti.")
        self.btn_mode_circle.setToolTip("Nakresli kružnicu: klik stred → ťahaj na polomer → pusti.")
        self.btn_mode_poly.setToolTip("Nakresli krivku: klikaj body, dvojklik ukončí, pravý klik vráti posledný bod.")
        self.spin_width.setToolTip("Šírka profilu okolo čiary/kruhu/krivky (px). Väčšia = tolerantnejšie vyhľadávanie hrán.")

        # --- klávesové skratky pre režimy ---
        QtWidgets.QShortcut(QtGui.QKeySequence("R"), self, activated=lambda: self._set_mode_safe("roi"))
        QtWidgets.QShortcut(QtGui.QKeySequence("M"), self, activated=lambda: self._set_mode_safe("mask"))
        QtWidgets.QShortcut(QtGui.QKeySequence("L"), self, activated=lambda: self._set_mode_safe("line"))
        QtWidgets.QShortcut(QtGui.QKeySequence("C"), self, activated=lambda: self._set_mode_safe("circle"))
        QtWidgets.QShortcut(QtGui.QKeySequence("K"), self, activated=lambda: self._set_mode_safe("polyline"))


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
        # NOVÉ tlačidlo: OK + NOK
        self.btn_autoteach_both = QtWidgets.QPushButton("Auto-teach z OK+NOK (optimálny prah)")

        self.btn_apply = QtWidgets.QPushButton("Použiť zmeny do nástroja")

        # Kontextová nápoveda
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
        right.addRow("", self.btn_autoteach_both)  # NOVÝ RIADOK
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
        self.btn_catalog.clicked.connect(self.open_tool_catalog)
        self.btn_del.clicked.connect(self.del_tool)
        self.btn_mode_roi.toggled.connect(self._on_mode_roi)
        self.btn_mode_mask.toggled.connect(self._on_mode_mask)
        self.btn_mode_line.toggled.connect(self._on_mode_line)
        self.btn_mode_circle.toggled.connect(self._on_mode_circle)
        self.btn_mode_poly.toggled.connect(self._on_mode_poly)

        self.spin_width.valueChanged.connect(self._on_width_changed)
        self.roi_view.shapeChanged.connect(self._on_shape_changed)

        self.btn_use_roi.clicked.connect(self.use_drawn_roi)
        self.btn_add_mask.clicked.connect(self.add_mask_from_drawn)
        self.btn_del_mask.clicked.connect(self.delete_selected_mask)
        self.btn_clear_masks.clicked.connect(self.clear_masks)

        self.list_masks.itemSelectionChanged.connect(self._on_mask_selected)
        self.list_masks.itemSelectionChanged.connect(self._update_mask_buttons)  # update stavov
        self.roi_view.maskAdded.connect(lambda *_: (self._refresh_mask_list(), self._update_mask_buttons()))
        self.btn_preset.clicked.connect(self.apply_preset)
        self.btn_apply.clicked.connect(self.apply_changes)
        self.btn_autoteach.clicked.connect(self.run_autoteach_ok_only)
        self.btn_autoteach_both.clicked.connect(self.run_autoteach_ok_nok)  # NOVÝ handler

        # Kontextová nápoveda – sleduj focus
        for w in (self.spin_thresh, self.spin_morph, self.spin_blob, self.cmb_measure,
                  self.dbl_lsl, self.dbl_usl, self.cmb_preset):
            w.installEventFilter(self)

    def _set_mode_icons(self):
        """Vygeneruje jednoduché vektorové ikonky (kreslené) pre režimy a nastaví ich na tlačidlá."""
        def make_icon(painter_fn):
            pm = QtGui.QPixmap(24, 24)
            pm.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(pm)
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            painter_fn(p)
            p.end()
            return QtGui.QIcon(pm)

        pen_roi    = QtGui.QPen(QtGui.QColor(33,150,243), 2)   # modrá
        pen_mask   = QtGui.QPen(QtGui.QColor(156,39,176), 2)   # fialová
        pen_shape  = QtGui.QPen(QtGui.QColor(255,193,7), 2)    # žltá

        def draw_rect(p):
            p.setPen(pen_roi)
            p.drawRect(4,4,16,16)

        def draw_mask(p):
            p.setPen(pen_mask)
            p.drawRect(4,4,16,16)
            p.fillRect(6,6,12,12, QtGui.QColor(156,39,176,60))

        def draw_line(p):
            p.setPen(pen_shape)
            p.drawLine(5,18,19,6)

        def draw_circle(p):
            p.setPen(pen_shape)
            p.drawEllipse(5,5,14,14)

        def draw_poly(p):
            p.setPen(pen_shape)
            path = QtGui.QPainterPath()
            path.moveTo(4,18); path.lineTo(10,8); path.lineTo(16,14); path.lineTo(20,6)
            p.drawPath(path)

        self.btn_mode_roi.setIcon(make_icon(draw_rect))
        self.btn_mode_mask.setIcon(make_icon(draw_mask))
        self.btn_mode_line.setIcon(make_icon(draw_line))
        self.btn_mode_circle.setIcon(make_icon(draw_circle))
        self.btn_mode_poly.setIcon(make_icon(draw_poly))

        # trochu miesta pre text + ikonku
        for b in (self.btn_mode_roi, self.btn_mode_mask, self.btn_mode_line, self.btn_mode_circle, self.btn_mode_poly):
            b.setIconSize(QtCore.QSize(20,20))


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
        self._update_mask_buttons()

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
            sk_typ = {
                "diff_from_ref":"Porovnanie s referenciou",
                "presence_absence":"Prítomnosť/Absencia",
                "yolo_roi":"YOLO v ROI",
                "_wip_edge_line":"Vada na priamke",
                "_wip_edge_circle":"Vada na kružnici",
                "_wip_edge_curve":"Vada na krivke",
            }.get(typ, typ)

            nm = t.get("name","Kontrola")
            usl = t.get("usl", None)
            self.list_tools.addItem(f"{sk_typ}  |  {nm}  |  USL={usl}")

    # ------------- UI handlers -------------
    def _on_tool_selected(self, row: int):
        self.current_tool_idx = row
        if row < 0:
            self._clear_form()
            self._update_mask_buttons()
            return

        t = self.recipe.get("tools", [])[row]
        typ = t.get("type","-")
        sk_typ = {
            "diff_from_ref":"Porovnanie s referenciou",
            "presence_absence":"Prítomnosť/Absencia",
            "yolo_roi":"YOLO v ROI",
            "_wip_edge_line":"Vada na priamke",
            "_wip_edge_circle":"Vada na kružnici",
            "_wip_edge_curve":"Vada na krivke",
        }.get(typ, typ)


        self.lbl_type.setText(sk_typ)
        self.edit_name.setText(t.get("name","Kontrola A"))
        self._update_ui_for_tool(typ)

        x,y,w,h = t.get("roi_xywh",[0,0,200,200])
        self.roi_view.set_roi(x,y,w,h)

        params = t.get("params",{}) or {}
        masks = params.get("mask_rects", []) or []
        self.roi_view.set_masks(masks)
        self._refresh_mask_list()

        # --- prepni kresliaci mód podľa typu nástroja ---
        if self._tool_needs_shape(typ):
            if typ == "_wip_edge_line":
                self.btn_mode_line.setChecked(True)
            elif typ == "_wip_edge_circle":
                self.btn_mode_circle.setChecked(True)
            elif typ == "_wip_edge_curve":
                self.btn_mode_poly.setChecked(True)
        else:
            self.btn_mode_roi.setChecked(True)

        # --- ak má nástroj shape parametre, zobraz ich v kresliacom widgete ---
        shape_dict = None
        if params.get("shape") == "line":
            shape_dict = {"shape":"line", "pts": params.get("pts", []), "width": params.get("width", self.spin_width.value())}
        elif params.get("shape") == "circle":
            shape_dict = {"shape":"circle", "cx": params.get("cx"), "cy": params.get("cy"), "r": params.get("r", 1), "width": params.get("width", self.spin_width.value())}
        elif params.get("shape") == "polyline":
            shape_dict = {"shape":"polyline", "pts": params.get("pts", []), "width": params.get("width", self.spin_width.value())}
        self.roi_view.set_shape(shape_dict)
        if shape_dict and "width" in shape_dict:
            try:
                self.spin_width.blockSignals(True)
                self.spin_width.setValue(int(shape_dict["width"]))
            finally:
                self.spin_width.blockSignals(False)


        # Metrológia
        self.dbl_lsl.setValue(t.get("lsl", 0.0) if t.get("lsl") is not None else 0.0)
        self.dbl_usl.setValue(t.get("usl", 200.0) if t.get("usl") is not None else 200.0)
        self.edit_units.setText(t.get("units","px²"))

        # Diff tool parametre (ostatné nástroje ich nepotrebujú)
        self.spin_thresh.setValue(int(params.get("thresh",35)))
        self.spin_morph.setValue(int(params.get("morph_open",1)))
        self.spin_blob.setValue(int(params.get("min_blob_area",120)))
        self.cmb_measure.setCurrentText("Plocha vád (px²)" if params.get("measure","area")=="area" else "Počet vád")

        is_diff = (typ == "diff_from_ref")
        # Parametrove polia a autoteach len pre diff
        for w in (self.spin_thresh, self.spin_morph, self.spin_blob, self.cmb_measure,
                  self.cmb_preset, self.btn_preset,
                  self.btn_autoteach, self.btn_autoteach_both):
            w.setEnabled(is_diff)

        # Maskovacie ovládanie je osobitne (pre diff + presence_absence + yolo_roi)
        self._update_mask_buttons()

    def _supports_shape(self, typ: str) -> bool:
        return typ in {"_wip_edge_line", "_wip_edge_circle", "_wip_edge_curve"}

    def _supports_masks(self, typ: str) -> bool:
        # masky teraz neaplikujeme pre edge-trace; zapnuté pre ostatné existujúce nástroje
        return typ in {"diff_from_ref", "presence_absence", "yolo_roi"}

    def _update_ui_for_tool(self, typ: str):
        """Podľa typu nástroja zobraz/skrývaj módy a tlačidlá."""
        shape = self._supports_shape(typ)
        masks = self._supports_masks(typ)

        # shape ovládanie
        self.btn_mode_line.setVisible(shape)
        self.btn_mode_circle.setVisible(shape)
        self.btn_mode_poly.setVisible(shape)
        self.spin_width.setVisible(shape)
        self.lbl_width.setVisible(shape)

        # mask ovládanie
        self.btn_mode_mask.setVisible(masks)
        self.btn_add_mask.setVisible(masks)
        self.btn_del_mask.setVisible(masks)
        self.btn_clear_masks.setVisible(masks)

        # ROI vždy viditeľné
        self.btn_mode_roi.setVisible(True)
        self.btn_use_roi.setVisible(True)

        # ak je práve zvolený skrytý mód, prepneme na ROI
        hidden_checked = any(b.isChecked() and not b.isVisible() for b in (
            self.btn_mode_mask, self.btn_mode_line, self.btn_mode_circle, self.btn_mode_poly
        ))
        if hidden_checked:
            self.btn_mode_roi.setChecked(True)



    def _on_mode_roi(self, checked: bool):
        self.roi_view.set_mode("roi" if checked else "mask")
        self.help_box.setPlainText(HELP_TEXTS["roi" if checked else "masks"])

    def _on_mode_mask(self, checked: bool):
        if checked:
            self.roi_view.set_mode("mask")
            self.help_box.setPlainText(HELP_TEXTS["masks"])

    def _on_mode_line(self, checked: bool):
        if checked:
            self.roi_view.set_mode("line")
            self.help_box.setPlainText("Režim ČIARA: klikni začiatok, potiahni a pusti. Dĺžka a poloha definujú trasu kontroly.")

    def _on_mode_circle(self, checked: bool):
        if checked:
            self.roi_view.set_mode("circle")
            self.help_box.setPlainText("Režim KRUŽNICA: klikni stred, potiahni na polomer a pusti. Kontrola prebieha po obvode.")

    def _on_mode_poly(self, checked: bool):
        if checked:
            self.roi_view.set_mode("polyline")
            self.help_box.setPlainText("Režim KRIVKA: klikaj body lomenej čiary, dvojklik ukončí, pravý klik vráti posledný bod.")

    def _on_width_changed(self, v: int):
        self.roi_view.set_stroke_width(int(v))
        # ak máme aktuálny shape-typ tool, priebežne aktualizuj width v parametri nástroja
        idx = self.current_tool_idx
        if idx is None or idx < 0: return
        t = self.recipe.get("tools", [])[idx]
        if self._tool_needs_shape(t.get("type","")):
            t.setdefault("params", {})
            t["params"]["width"] = int(v)

    def _on_shape_changed(self, shape: dict):
        """Z ROIDrawer-u pri dokončení kresby: uloží shape do params vybraného nástroja."""
        idx = self.current_tool_idx
        if idx is None or idx < 0: return
        t = self.recipe["tools"][idx]
        if not self._tool_needs_shape(t.get("type","")):
            return
        p = t.setdefault("params", {})
        s = (shape or {}).copy()
        kind = s.get("shape")
        if kind == "line":
            p["shape"] = "line"
            p["pts"] = s.get("pts", [])
            p["width"] = s.get("width", self.spin_width.value())
        elif kind == "circle":
            p["shape"] = "circle"
            p["cx"] = s.get("cx"); p["cy"] = s.get("cy"); p["r"] = s.get("r", 1)
            p["width"] = s.get("width", self.spin_width.value())
        elif kind == "polyline":
            p["shape"] = "polyline"
            p["pts"] = s.get("pts", [])
            p["width"] = s.get("width", self.spin_width.value())

    def _set_mode_safe(self, mode: str):
        mapping = {
            "roi": self.btn_mode_roi,
            "mask": self.btn_mode_mask,
            "line": self.btn_mode_line,
            "circle": self.btn_mode_circle,
            "polyline": self.btn_mode_poly,
        }
        btn = mapping.get(mode)
        if not btn or not btn.isVisible() or not btn.isEnabled():
            return
        btn.setChecked(True)


    def _tool_needs_shape(self, typ: str) -> bool:
        return typ in {"_wip_edge_line", "_wip_edge_circle", "_wip_edge_curve"}


    def _on_mask_selected(self):
        idx = self.list_masks.currentRow()
        self.roi_view.set_active_mask_index(idx)

    def use_drawn_roi(self):
        if not self.roi_view._roi:
            QtWidgets.QMessageBox.information(self, "ROI", "Nakresli ROI v režime ROI.")
            return
        QtWidgets.QMessageBox.information(self, "ROI", "ROI nastavené. Klikni „Použiť zmeny do nástroja“ a potom „Uložiť verziu“.")

    def add_mask_from_drawn(self):
        if not self._tool_allows_masks():
            return
        rect = getattr(self.roi_view, "_temp_rect", None) or self.roi_view._roi
        if not rect:
            QtWidgets.QMessageBox.information(self, "Maska", "Nakresli obdĺžnik v režime MASKA (fialová).")
            return
        x,y,w,h = rect
        self.roi_view.add_mask_rect(x,y,w,h)
        self._refresh_mask_list()
        self._update_mask_buttons()

    def delete_selected_mask(self):
        if not self._tool_allows_masks():
            return
        row = self.list_masks.currentRow()
        if row < 0: return
        masks = self.roi_view.masks()
        del masks[row]
        self.roi_view.set_masks(masks)
        self._refresh_mask_list()
        self._update_mask_buttons()

    def clear_masks(self):
        if not self._tool_allows_masks():
            return
        self.roi_view.clear_masks()
        self._refresh_mask_list()
        self._update_mask_buttons()

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
        else:
            # aj pre Presence/Absence a YOLO chceme uložiť masky:
            new["params"] = {"mask_rects":[]}
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
        self._update_mask_buttons()

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

        # Ukladaj masky pre VŠETKY podporované nástroje
        p = t.setdefault("params", {})
        p["mask_rects"] = [[int(a) for a in r] for r in self.roi_view.masks()]

        # Diff-specific parametre
        if t.get("type") == "diff_from_ref":
            p["thresh"] = int(self.spin_thresh.value())
            p["morph_open"] = int(self.spin_morph.value())
            p["min_blob_area"] = int(self.spin_blob.value())
            p["measure"] = "area" if self.cmb_measure.currentText().startswith("Plocha") else "count"

        self._refresh_tool_list()
        QtWidgets.QMessageBox.information(self, "OK", "Zmeny aplikované. Nezabudni „Uložiť verziu“.")

    def open_tool_catalog(self):
        """
        ELI5: Otvorí katalóg, user vyberie nástroj, my ho vložíme do receptu
        s rozumnými defaultmi. ROI a masky si potom user doladí v Builderi.
        """
        dlg = ToolCatalogDialog(self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        tpl = dlg.selected_template()
        if not tpl:
            return

        # mapovanie template -> tool dict v recepte
        new_tool = self._template_to_tool(tpl)

        self.recipe.setdefault("tools", []).append(new_tool)
        self._refresh_tool_list()
        self.list_tools.setCurrentRow(self.list_tools.count()-1)
        QtWidgets.QMessageBox.information(self, "Pridané", f"Nástroj „{tpl.get('title','?')}“ bol pridaný. Nastav ROI/masky a klikni „Použiť zmeny…“, potom „Uložiť verziu“.")

    def _template_to_tool(self, tpl: dict) -> dict:
        """
        Z tool šablóny (katalóg) urobí zápis do receptu.
        Štartovacie ROI dáme malé [0,0,200,200], user si hneď upraví.
        """
        typ = tpl.get("type", "diff_from_ref")
        name = tpl.get("title", "Kontrola")
        units = tpl.get("units", "px²" if typ=="diff_from_ref" else "ks")
        params = dict(tpl.get("params", {}) or {})

        # default masky pole, ak náhodou nie je
        params.setdefault("mask_rects", [])

        tool = {
            "type": typ,
            "name": name,
            "roi_xywh": [0,0,200,200],
            "params": params,
            "lsl": None,
            "usl": 200.0 if typ=="diff_from_ref" else None,
            "units": units
        }
        return tool

    # ---------- Auto-teach: OK len ----------
    def run_autoteach_ok_only(self):
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
        imgs = sorted(list(ok_dir.glob("*.png")) + list(ok_dir.glob("*.jpg")) + list(ok_dir.glob("*.bmp")))
        for pth in imgs:
            cur = cv.imread(str(pth), cv.IMREAD_GRAYSCALE)
            if cur is None: continue
            r = tool.run(ref, cur, fixture_transform=None)
            vals.append(float(r.measured))
        if not vals:
            QtWidgets.QMessageBox.warning(self, "Auto-teach", "Nenašiel som použiteľné OK snímky.")
            return
        vals = np.array(vals, dtype=float)
        perc = 100.0 * (1.0 - float(self.spin_fpr.value()))
        usl = float(np.percentile(vals, perc))
        self.dbl_usl.setValue(usl)
        QtWidgets.QMessageBox.information(self, "Auto-teach", f"USL = {usl:.2f} (len OK, FPR≈{float(self.spin_fpr.value()):.4f}). Klikni „Použiť zmeny“ a potom „Uložiť verziu“.")

    # ---------- Auto-teach: OK + NOK ----------
    def run_autoteach_ok_nok(self):
        name = self.edit_recipe.text().strip()
        ok_dir  = Path("datasets")/name/"ok"
        nok_dir = Path("datasets")/name/"nok"
        if not ok_dir.exists():
            QtWidgets.QMessageBox.warning(self, "Auto-teach", f"Chýbajú OK snímky v {ok_dir}")
            return
        if not nok_dir.exists():
            # fallback: použijeme OK-only
            return self.run_autoteach_ok_only()

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
        if t.get("type") != "diff_from_ref":
            QtWidgets.QMessageBox.warning(self, "Auto-teach", "OK+NOK prahovanie má zmysel pre Porovnanie s referenciou.")
            return

        from core.tools.diff_from_ref import DiffFromRefTool
        tool = DiffFromRefTool(
            name=t.get("name","Kontrola"),
            roi_xywh=tuple(t.get("roi_xywh",[0,0,200,200])),
            params=t.get("params",{}),
            lsl=t.get("lsl"), usl=t.get("usl"),
            units=t.get("units","px²")
        )

        def load_vals(d: Path):
            imgs = sorted(list(d.glob("*.png")) + list(d.glob("*.jpg")) + list(d.glob("*.bmp")))
            out=[]
            for p in imgs:
                cur = cv.imread(str(p), cv.IMREAD_GRAYSCALE)
                if cur is None: continue
                r = tool.run(ref, cur, fixture_transform=None)
                out.append(float(r.measured))
            return np.array(out, dtype=float)

        m_ok  = load_vals(ok_dir)
        m_nok = load_vals(nok_dir)

        if m_ok.size == 0:
            QtWidgets.QMessageBox.warning(self, "Auto-teach", "OK dataset prázdny.")
            return
        if m_nok.size == 0:
            QtWidgets.QMessageBox.information(self, "Auto-teach", "NOK dataset prázdny – použijem OK-only.")
            return self.run_autoteach_ok_only()

        # Kandidátne prahy – spájame a triedime
        candidates = np.unique(np.concatenate([m_ok, m_nok]))
        if candidates.size > 2000:  # zrýchlenie: sub-sampling
            candidates = np.linspace(candidates.min(), candidates.max(), 2000)

        # Optimalizácia prahu
        target_fpr = float(self.spin_fpr.value())  # horný limit FPR
        best = None
        best_key = None  # tuple pre triedenie (primárne FPR<=target, max J; sekundárne max TPR)
        n_ok  = m_ok.size
        n_nok = m_nok.size

        for tval in candidates:
            # „vyššie horšie“ → prah je USL: NOK ak m > t
            tp = np.sum(m_nok > tval)   # správne chytené NOK
            fn = np.sum(m_nok <= tval)  # nechytené NOK
            fp = np.sum(m_ok  > tval)   # falošné poplachy
            tn = np.sum(m_ok  <= tval)

            tpr = tp / n_nok if n_nok else 0.0   # citlivosť
            fpr = fp / n_ok  if n_ok  else 0.0
            tnr = 1.0 - fpr
            J   = tpr + tnr - 1.0

            # Primárne chceme držať fpr <= target; potom max J; ako sekundárne max tpr
            key = None
            if fpr <= target_fpr:
                key = (0, -J, -tpr)    # 0 = OK (spĺňa limit), potom max J, max TPR
            else:
                key = (1, fpr, -J)     # 1 = penalizácia (nespĺňa), minimalizuj FPR potom max J

            if best_key is None or key < best_key:
                best_key = key
                best = (tval, tpr, fpr, J)

        if best is None:
            QtWidgets.QMessageBox.warning(self, "Auto-teach", "Nepodarilo sa nájsť prah.")
            return

        usl, tpr, fpr, J = best
        self.dbl_usl.setValue(float(usl))
        QtWidgets.QMessageBox.information(
            self, "Auto-teach (OK+NOK)",
            f"USL = {usl:.2f}\n"
            f"TPR (zachytenie NOK) = {tpr*100:.1f} %\n"
            f"FPR (falošné OK→NOK) = {fpr*100:.2f} %\n"
            f"J = {J:.3f}\n\n"
            "Klikni „Použiť zmeny“ a potom „Uložiť verziu“."
        )
