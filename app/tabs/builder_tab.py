# app/tabs/builder_tab.py
from PyQt5 import QtWidgets, QtCore, QtGui
from pathlib import Path
import numpy as np
import cv2 as cv

from app.widgets.preproc_catalog import PreprocDialog
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
try:
    from core.tools.edge_trace import EdgeTraceLineTool, EdgeTraceCircleTool, EdgeTraceCurveTool
except Exception:
    EdgeTraceLineTool = EdgeTraceCircleTool = EdgeTraceCurveTool = None


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

# Diff presety (porovnanie s referenciou)
DIFF_PRESETS = {
    "Plast (matný)":        {"thresh": 35, "morph": 1, "blob": 120, "measure":"area"},
    "Plast (lesklý)":       {"thresh": 45, "morph": 1, "blob": 200, "measure":"area"},
    "Kov (matný)":          {"thresh": 40, "morph": 1, "blob": 150, "measure":"area"},
    "Kov (lesklý)":         {"thresh": 55, "morph": 2, "blob": 300, "measure":"area"},
    "Guma / NIR":           {"thresh": 35, "morph": 1, "blob": 180, "measure":"area"},
    "Hrubé vady 1mm+":      {"thresh": 50, "morph": 1, "blob": 500, "measure":"area"},
    "Citlivé (laboratórne)":{"thresh": 25, "morph": 0, "blob": 60,  "measure":"area"},
}

# Edge-trace presety (čiara/kružnica/krivka)
EDGE_PRESETS = {
    "Hrany – mäkké":     {"canny_lo": 20, "canny_hi":  80, "width": 5, "metric": "coverage_pct"},
    "Hrany – štandard":  {"canny_lo": 40, "canny_hi": 120, "width": 3, "metric": "coverage_pct"},
    "Hrany – agresívne": {"canny_lo": 60, "canny_hi": 180, "width": 2, "metric": "px_gap"},
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

        # --- Náhľad zobrazenia (ako v RUN) ---
        row_view = QtWidgets.QHBoxLayout()
        row_view.addWidget(QtWidgets.QLabel("Náhľad:"))
        self.cmb_view = QtWidgets.QComboBox()
        self.cmb_view.addItems(["Štandard", "ROI po preproc", "ROI bez preproc", "Čistý obraz"])
        row_view.addWidget(self.cmb_view, 1)
        mid.addLayout(row_view)

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
        self._form_right = right  # aby sme mali referenciu, keby sme chceli neskôr pracovať s labelmi
        self.lbl_type = QtWidgets.QLabel("-")
        self.edit_name = QtWidgets.QLineEdit("Kontrola A")

        # Presety
        self.cmb_preset = QtWidgets.QComboBox()   # položky doplníme podľa typu nástroja
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

        # --- Skupiny parametrov podľa nástroja (default skryté / ukazujeme podľa výberu) ---

        # 0) Diff (porovnanie s referenciou) – wrapper, aby sa dal skryť naraz
        self.grp_diff = QtWidgets.QWidget()
        g_diff = QtWidgets.QFormLayout(self.grp_diff)
        g_diff.setContentsMargins(0,0,0,0)
        g_diff.addRow("Citlivosť (prahovanie):", self.spin_thresh)
        g_diff.addRow("Čistenie šumu (morf. open):", self.spin_morph)
        g_diff.addRow("Min. plocha defektu (px²):", self.spin_blob)
        g_diff.addRow("Metóda merania:", self.cmb_measure)

        # 1) Edge-trace (čiara/kružnica/krivka)
        self.grp_edge = QtWidgets.QWidget()
        g_edge = QtWidgets.QFormLayout(self.grp_edge)
        self.spin_canny_lo = QtWidgets.QSpinBox(); self.spin_canny_lo.setRange(0,255); self.spin_canny_lo.setValue(40)
        self.spin_canny_hi = QtWidgets.QSpinBox(); self.spin_canny_hi.setRange(0,255); self.spin_canny_hi.setValue(120)
        self.cmb_metric = QtWidgets.QComboBox(); self.cmb_metric.addItems(["px_gap (menej=lepšie)", "coverage_pct (viac=lepšie)"])
        self.cmb_metric.currentIndexChanged.connect(self._on_metric_changed)

        self.grp_edge.setToolTip("Parametre vyhodnocovania hrán v páse okolo nakreslenej čiary/kruhu/krivky.")
        g_edge.addRow("Canny low:", self.spin_canny_lo)
        g_edge.addRow("Canny high:", self.spin_canny_hi)
        g_edge.addRow("Metrika:", self.cmb_metric)

        # 2) Presence/Absence
        self.grp_presence = QtWidgets.QWidget()
        g_pa = QtWidgets.QFormLayout(self.grp_presence)
        self.dbl_minScore = QtWidgets.QDoubleSpinBox(); self.dbl_minScore.setRange(0.0, 1.0); self.dbl_minScore.setDecimals(3); self.dbl_minScore.setSingleStep(0.01); self.dbl_minScore.setValue(0.70)
        self.grp_presence.setToolTip("Minimálne skóre zhody šablóny v ROI.")
        g_pa.addRow("Min. skóre:", self.dbl_minScore)

        # 3) YOLO v ROI
        self.grp_yolo = QtWidgets.QWidget()
        g_y = QtWidgets.QFormLayout(self.grp_yolo)
        self.dbl_conf = QtWidgets.QDoubleSpinBox(); self.dbl_conf.setRange(0.0, 1.0); self.dbl_conf.setSingleStep(0.01); self.dbl_conf.setValue(0.25)
        self.dbl_iou  = QtWidgets.QDoubleSpinBox(); self.dbl_iou.setRange(0.0, 1.0);  self.dbl_iou.setSingleStep(0.01);  self.dbl_iou.setValue(0.45)
        self.spin_max_det = QtWidgets.QSpinBox(); self.spin_max_det.setRange(1, 2000); self.spin_max_det.setValue(100)
        self.grp_yolo.setToolTip("Parametre NMS a dôveryhodnosti modelu YOLO.")
        g_y.addRow("Conf threshold:", self.dbl_conf)
        g_y.addRow("IoU threshold:", self.dbl_iou)
        g_y.addRow("Max detections:", self.spin_max_det)

        # 2b) Blob-count (počet objektov)
        self.grp_blob = QtWidgets.QWidget()
        g_blob = QtWidgets.QFormLayout(self.grp_blob)
        self.spin_min_area = QtWidgets.QSpinBox(); self.spin_min_area.setRange(0, 100000); self.spin_min_area.setValue(120)
        self.chk_invert = QtWidgets.QCheckBox("Invertovať po Otsu")
        self.grp_blob.setToolTip("Počítanie objektov v ROI po binarizácii. Menšie bloby ako 'min. plocha' sa ignorujú.")
        g_blob.addRow("Min. plocha [px²]:", self.spin_min_area)
        g_blob.addRow("", self.chk_invert)

        # default: skryť všetky skupiny – do FormLayoutu ich pridávame nižšie v sekcii „Jednotné poradie“
        for grp in (self.grp_diff, self.grp_edge, self.grp_presence, self.grp_yolo, self.grp_blob):
            grp.hide()



        # NOVÉ tlačidlo: OK + NOK
        self.btn_autoteach_both = QtWidgets.QPushButton("Auto-teach z OK+NOK (optimálny prah)")

        self.btn_apply = QtWidgets.QPushButton("Použiť zmeny do nástroja")

        # Kontextová nápoveda
        self.help_box = QtWidgets.QTextEdit()
        self.help_box.setReadOnly(True)
        self.help_box.setMinimumHeight(120)
        self.help_box.setStyleSheet("QTextEdit{background:#111; color:#ddd; border-radius:8px; padding:8px;}")

        # ---- JEDNOTNÉ PORADIE V PRAVOM PANELI ----
        right.addRow("<b>Typ nástroja</b>", self.lbl_type)

        # 1) Predvoľba (hneď po type)
        right.addRow("Predvoľba", self.cmb_preset)
        right.addRow("", self.btn_preset)
                # --- Predspracovanie (katalóg presetov) ---
        self.btn_preproc = QtWidgets.QPushButton("Predspracovanie…")
        self.lbl_preproc = QtWidgets.QLabel("—")
        self.lbl_preproc.setStyleSheet("color:#aaa;")
        right.addRow("Predspracovanie", self.btn_preproc)
        right.addRow("Reťazec", self.lbl_preproc)

        right.addRow(QtWidgets.QLabel("<hr>"))

        # 2) Názov (praktické dať sem, po predvoľbe)
        right.addRow("Názov (krátko)", self.edit_name)

        right.addRow(QtWidgets.QLabel("<hr>"))

        # 3) Parametre nástroja (kontextové skupiny)
        right.addRow(QtWidgets.QLabel("<b>Parametre nástroja</b>"))
        # (Tieto skupiny si vytvoril vyššie v _build(): self.grp_diff / self.grp_edge / self.grp_presence / self.grp_yolo)
        right.addRow(self.grp_diff)
        right.addRow(self.grp_edge)
        right.addRow(self.grp_presence)
        right.addRow(self.grp_yolo)
        right.addRow(self.grp_blob)


        right.addRow(QtWidgets.QLabel("<hr>"))

        # 4) Limity a jednotky
        right.addRow("Spodná hranica (LSL)", self.dbl_lsl)
        right.addRow("Horná hranica (USL)", self.dbl_usl)
        right.addRow("Jednotky", self.edit_units)

        right.addRow(QtWidgets.QLabel("<hr>"))

        # 5) Akcia – uložiť zmeny do nástroja
        right.addRow("", self.btn_apply)

        right.addRow(QtWidgets.QLabel("<hr>"))

        # 6) Cieľová FPR (predposledné) + Auto-teach tlačidlá
        right.addRow("Cieľová FPR", self.spin_fpr)
        right.addRow("", self.btn_autoteach)
        right.addRow("", self.btn_autoteach_both)

        right.addRow(QtWidgets.QLabel("<hr>"))

        # 7) Nápoveda (posledné)
        right.addRow("Nápoveda", self.help_box)

        # (Nezabudni: kontextové skupiny skry/ukáž v _update_ui_for_tool(typ)
        #  self.grp_diff.setVisible(is_diff), self.grp_edge.setVisible(shape), atď.)


        layout.addLayout(left, 1)
        layout.addLayout(mid, 1)
        layout.addLayout(right, 1)

        # Signály
        btn_load.clicked.connect(self.load_recipe)
        btn_save.clicked.connect(self.save_recipe)
        self.list_tools.currentRowChanged.connect(self._on_tool_selected)
        self.btn_catalog.clicked.connect(self.open_tool_catalog)
        self.btn_preproc.clicked.connect(self.open_preproc_dialog)
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
        self.cmb_view.currentIndexChanged.connect(self._update_preview_image)
        self.roi_view.roiChanged.connect(lambda *_: self._update_preview_image())
        self.roi_view.masksChanged.connect(self._update_preview_image)

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
            self._update_preview_image()
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
            self._update_preview_image()

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
        self._update_preview_image()

        x,y,w,h = t.get("roi_xywh",[0,0,200,200])
        self.roi_view.set_roi(x,y,w,h)

        params = t.get("params",{}) or {}

        # preproc zhrnutie
        pre = params.get("preproc", []) or []
        self.lbl_preproc.setText(self._preproc_summary(pre))

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

        # --- Edge-trace params ---
        self.spin_canny_lo.setValue(int(params.get("canny_lo", 40)))
        self.spin_canny_hi.setValue(int(params.get("canny_hi", 120)))
        metric = str(params.get("metric", "px_gap")).lower()
        self.cmb_metric.setCurrentText("coverage_pct (viac=lepšie)" if metric=="coverage_pct" else "px_gap (menej=lepšie)")
        # prepnime aj jednotky
        if metric == "coverage_pct":
            self.edit_units.setText("%")
        elif self.edit_units.text().strip() == "%":
            self.edit_units.setText("px")

        # --- Presence/Absence ---
        self.dbl_minScore.setValue(float(params.get("minScore", 0.70)))

        # --- YOLO v ROI ---
        self.dbl_conf.setValue(float(params.get("conf_thres", 0.25)))
        self.dbl_iou.setValue(float(params.get("iou_thres", 0.45)))
        self.spin_max_det.setValue(int(params.get("max_det", 100)))

        # --- Blob-count ---
        self.spin_min_area.setValue(int(params.get("min_area", 120)))
        self.chk_invert.setChecked(bool(params.get("invert", False)))

        # --- Zapni/Skry UI skupiny podľa typu ---
        self._update_ui_for_tool(typ)


        is_diff = (typ == "diff_from_ref")
        is_edge = self._supports_shape(typ)

        # Diff-only polia
        for w in (self.spin_thresh, self.spin_morph, self.spin_blob, self.cmb_measure):
            w.setEnabled(is_diff)

        # Presety a Auto-teach: povoliť pre diff aj edge
        for w in (self.cmb_preset, self.btn_preset, self.btn_autoteach, self.btn_autoteach_both):
            w.setEnabled(is_diff or is_edge)

        # Naplň zoznam presetov podľa typu
        self._load_presets_for_type(typ)


        # Maskovacie ovládanie je osobitne (pre diff + presence_absence + yolo_roi)
        self._update_mask_buttons()

    def _load_presets_for_type(self, typ: str):
        """Naplní combo Predvoľba podľa typu nástroja."""
        self.cmb_preset.clear()
        if (typ or "").lower() in {"_wip_edge_line", "_wip_edge_circle", "_wip_edge_curve"}:
            self.cmb_preset.addItems(list(EDGE_PRESETS.keys()))
        else:
            self.cmb_preset.addItems(list(DIFF_PRESETS.keys()))

    def _apply_edge_preset(self, p: dict):
        """Aplikuje edge preset do UI (bez potreby hneď klikať Použiť zmeny)."""
        if not p: return
        self.spin_canny_lo.setValue(int(p.get("canny_lo", 40)))
        self.spin_canny_hi.setValue(int(p.get("canny_hi", 120)))
        self.spin_width.setValue(int(p.get("width", 3)))
        met = str(p.get("metric", "coverage_pct")).lower()
        self.cmb_metric.setCurrentText("coverage_pct (viac=lepšie)" if met=="coverage_pct" else "px_gap (menej=lepšie)")
        # jednotky podľa metriky
        if met == "coverage_pct" and self.edit_units.text().strip() != "%":
            self.edit_units.setText("%")
        elif met != "coverage_pct" and self.edit_units.text().strip() == "%":
            self.edit_units.setText("px")

    def _on_metric_changed(self, *_):
        """Keď užívateľ prepne metriku edge-trace, prepneme aj jednotky."""
        txt = self.cmb_metric.currentText().lower()
        if "coverage_pct" in txt:
            if self.edit_units.text().strip() != "%":
                self.edit_units.setText("%")
        else:
            if self.edit_units.text().strip() == "%":
                self.edit_units.setText("px")


    def _supports_shape(self, typ: str) -> bool:
        return (typ or "").lower() in {"_wip_edge_line", "_wip_edge_circle", "_wip_edge_curve"}

    def _supports_masks(self, typ: str) -> bool:
        return (typ or "").lower() in {"diff_from_ref", "presence_absence", "yolo_roi", "blob_count"}

    def _supports_diff(self, typ: str) -> bool:
        return (typ or "").lower() == "diff_from_ref"

    def _supports_presence(self, typ: str) -> bool:
        return (typ or "").lower() == "presence_absence"

    def _supports_yolo(self, typ: str) -> bool:
        return (typ or "").lower() == "yolo_roi"

    def _update_ui_for_tool(self, typ: str):
        """Podľa typu nástroja zobraz/skrývaj režimy a parametrové skupiny."""
        shape = self._supports_shape(typ)
        masks = self._supports_masks(typ)
        is_diff = self._supports_diff(typ)
        is_pa   = self._supports_presence(typ)
        is_yolo = self._supports_yolo(typ)
        is_blob = (typ or "").lower() == "blob_count"

        # shape ovládanie (štetce + šírka profilu)
        self.btn_mode_line.setVisible(shape)
        self.btn_mode_circle.setVisible(shape)
        self.btn_mode_poly.setVisible(shape)
        self.spin_width.setVisible(shape)
        self.lbl_width.setVisible(shape)

        # mask ovládanie a tlačidlá
        self.btn_mode_mask.setVisible(masks)
        self.btn_add_mask.setVisible(masks)
        self.btn_del_mask.setVisible(masks)
        self.btn_clear_masks.setVisible(masks)

        # diff parametre – skry/ukáž celú skupinu aj s popiskami
        self.grp_diff.setVisible(is_diff)


        # nové skupiny parametrov
        self.grp_edge.setVisible(shape)
        self.grp_presence.setVisible(is_pa)
        self.grp_yolo.setVisible(is_yolo)
        self.grp_blob.setVisible(is_blob)

        # ROI a „Použiť zmeny“ nech sú stále viditeľné
        self.btn_mode_roi.setVisible(True)
        self.btn_use_roi.setVisible(True)
        self.btn_apply.setVisible(True)

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
        typ = (self._active_tool_type() or "").lower()
        if typ in {"_wip_edge_line", "_wip_edge_circle", "_wip_edge_curve"}:
            p = EDGE_PRESETS.get(name)
            if not p: return
            self._apply_edge_preset(p)
        else:
            p = DIFF_PRESETS.get(name)
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

        # Edge-trace parametre
        elif t.get("type") in {"_wip_edge_line", "_wip_edge_circle", "_wip_edge_curve"}:
            p["canny_lo"] = int(self.spin_canny_lo.value())
            p["canny_hi"] = int(self.spin_canny_hi.value())
            p["metric"] = "coverage_pct" if self.cmb_metric.currentText().startswith("coverage") else "px_gap"

        # Presence/Absence parametre
        elif t.get("type") == "presence_absence":
            p["minScore"] = float(self.dbl_minScore.value())

        # YOLO v ROI parametre
        elif t.get("type") == "yolo_roi":
            p["conf_thres"] = float(self.dbl_conf.value())
            p["iou_thres"]  = float(self.dbl_iou.value())
            p["max_det"]    = int(self.spin_max_det.value())

        elif t.get("type") == "blob_count":
            p["min_area"] = int(self.spin_min_area.value())
            p["invert"]   = bool(self.chk_invert.isChecked())

                    
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
        typ = (t.get("type","") or "").lower()
        params = dict(t.get("params",{}) or {})
        roi = tuple(t.get("roi_xywh",[0,0,200,200]))

        # --- DIFF --------------------------------------------------------
        if typ == "diff_from_ref":
            from core.tools.diff_from_ref import DiffFromRefTool
            tool = DiffFromRefTool(name=t.get("name","Kontrola"), roi_xywh=roi,
                                params=params, lsl=t.get("lsl"), usl=t.get("usl"),
                                units=t.get("units","px²"))
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
            return

        # --- EDGE-TRACE --------------------------------------------------
        if typ in {"_wip_edge_line","_wip_edge_circle","_wip_edge_curve"}:
            # instance správneho edge toolu
            cls_map = {
                "_wip_edge_line": EdgeTraceLineTool,
                "_wip_edge_circle": EdgeTraceCircleTool,
                "_wip_edge_curve": EdgeTraceCurveTool,
            }
            ToolCls = cls_map.get(typ)
            if ToolCls is None:
                QtWidgets.QMessageBox.warning(self, "Auto-teach", "Edge nástroj nie je dostupný.")
                return

            # použijeme aktuálne UI hodnoty (ak ich user menil a ešte nestlačil „Použiť zmeny“)
            params = dict(params)
            params["canny_lo"] = int(self.spin_canny_lo.value())
            params["canny_hi"] = int(self.spin_canny_hi.value())
            params["width"]    = int(self.spin_width.value())
            params["metric"]   = "coverage_pct" if self.cmb_metric.currentText().startswith("coverage") else "px_gap"

            tool = ToolCls(name=t.get("name","Edge"), roi_xywh=roi, params=params,
                        lsl=t.get("lsl"), usl=t.get("usl"),
                        units=t.get("units","% " if params["metric"]=="coverage_pct" else "px"))

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
            metric = params["metric"]
            if metric == "px_gap":
                # menšie lepšie → nastavíme USL na (1-FPR) percentil
                perc = 100.0 * (1.0 - float(self.spin_fpr.value()))
                usl = float(np.percentile(vals, perc))
                self.dbl_lsl.setValue(0.0)              # typicky None, ale necháme 0
                self.dbl_usl.setValue(usl)
                if self.edit_units.text().strip() == "%":
                    self.edit_units.setText("px")
                QtWidgets.QMessageBox.information(self, "Auto-teach (edge, OK)", f"USL = {usl:.2f} (FPR≈{float(self.spin_fpr.value()):.4f}).")
            else:
                # coverage_pct → väčšie lepšie → nastavíme LSL na FPR percentil
                perc = 100.0 * float(self.spin_fpr.value())
                lsl = float(np.percentile(vals, perc))
                self.dbl_lsl.setValue(lsl)
                self.dbl_usl.setValue(1e9)              # alebo None; necháme veľké číslo
                self.edit_units.setText("%")
                QtWidgets.QMessageBox.information(self, "Auto-teach (edge, OK)", f"LSL = {lsl:.2f}% (FPR≈{float(self.spin_fpr.value()):.4f}).")
            return

        # iné typy – zatiaľ nepodporujeme OK-only auto-teach
        QtWidgets.QMessageBox.information(self, "Auto-teach", "Auto-teach je zatiaľ pre Porovnanie s referenciou a Edge nástroje.")

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
        typ = (t.get("type") or "").lower()

        ref_path = self.recipe.get("reference_image", None)
        if not ref_path or not Path(ref_path).exists():
            QtWidgets.QMessageBox.warning(self, "Auto-teach", "Chýba referenčný obrázok v recepte.")
            return
        ref = cv.imread(ref_path, cv.IMREAD_GRAYSCALE)

        # --- helper na načítanie meraní pre ľubovoľný tool ---
        def measure_all(tool_factory, d: Path):
            imgs = sorted(list(d.glob("*.png")) + list(d.glob("*.jpg")) + list(d.glob("*.bmp")))
            out=[]
            for p in imgs:
                cur = cv.imread(str(p), cv.IMREAD_GRAYSCALE)
                if cur is None: continue
                r = tool_factory().run(ref, cur, fixture_transform=None)
                out.append(float(r.measured))
            return np.array(out, dtype=float)

        roi = tuple(t.get("roi_xywh",[0,0,200,200]))
        params = dict(t.get("params",{}) or {})

        if typ == "diff_from_ref":
            from core.tools.diff_from_ref import DiffFromRefTool
            def make_diff():
                return DiffFromRefTool(name=t.get("name","Kontrola"), roi_xywh=roi,
                                    params=params, lsl=t.get("lsl"), usl=t.get("usl"),
                                    units=t.get("units","px²"))
            m_ok  = measure_all(lambda: make_diff(), ok_dir)
            m_nok = measure_all(lambda: make_diff(), nok_dir)
            larger_is_worse = True   # viac plochy vád = horšie
            metric_name = "diff"
        elif typ in {"_wip_edge_line","_wip_edge_circle","_wip_edge_curve"}:
            cls_map = {
                "_wip_edge_line": EdgeTraceLineTool,
                "_wip_edge_circle": EdgeTraceCircleTool,
                "_wip_edge_curve": EdgeTraceCurveTool,
            }
            ToolCls = cls_map.get(typ)
            if ToolCls is None:
                QtWidgets.QMessageBox.warning(self, "Auto-teach", "Edge nástroj nie je dostupný.")
                return
            # override param z UI
            params["canny_lo"] = int(self.spin_canny_lo.value())
            params["canny_hi"] = int(self.spin_canny_hi.value())
            params["width"]    = int(self.spin_width.value())
            params["metric"]   = "coverage_pct" if self.cmb_metric.currentText().startswith("coverage") else "px_gap"
            def make_edge():
                return ToolCls(name=t.get("name","Edge"), roi_xywh=roi, params=params,
                            lsl=t.get("lsl"), usl=t.get("usl"),
                            units=t.get("units","% " if params["metric"]=="coverage_pct" else "px"))
            m_ok  = measure_all(lambda: make_edge(), ok_dir)
            m_nok = measure_all(lambda: make_edge(), nok_dir)
            # pre klasifikáciu:
            larger_is_worse = (params["metric"] == "px_gap")   # gap: viac = horšie; coverage: menej = horšie
            metric_name = params["metric"]
        else:
            QtWidgets.QMessageBox.information(self, "Auto-teach", "OK+NOK auto-teach je zatiaľ pre diff a edge.")
            return

        if m_ok.size == 0:
            QtWidgets.QMessageBox.warning(self, "Auto-teach", "OK dataset prázdny.")
            return
        if m_nok.size == 0:
            QtWidgets.QMessageBox.information(self, "Auto-teach", "NOK dataset prázdny – použijem OK-only.")
            return self.run_autoteach_ok_only()

        # Kandidátne prahy
        candidates = np.unique(np.concatenate([m_ok, m_nok]))
        if candidates.size > 2000:
            candidates = np.linspace(candidates.min(), candidates.max(), 2000)

        target_fpr = float(self.spin_fpr.value())
        best = None; best_key=None
        n_ok, n_nok = m_ok.size, m_nok.size

        for thr in candidates:
            if larger_is_worse:
                # NOK ak m > thr
                tp = np.sum(m_nok > thr); fn = np.sum(m_nok <= thr)
                fp = np.sum(m_ok  > thr); tn = np.sum(m_ok  <= thr)
            else:
                # NOK ak m < thr
                tp = np.sum(m_nok < thr); fn = np.sum(m_nok >= thr)
                fp = np.sum(m_ok  < thr); tn = np.sum(m_ok  >= thr)

            tpr = tp/n_nok if n_nok else 0.0
            fpr = fp/n_ok  if n_ok  else 0.0
            tnr = 1.0 - fpr
            J = tpr + tnr - 1.0

            if fpr <= target_fpr:
                key = (0, -J, -tpr)
            else:
                key = (1, fpr, -J)
            if best_key is None or key < best_key:
                best_key = key; best = (thr, tpr, fpr, J)

        if best is None:
            QtWidgets.QMessageBox.warning(self, "Auto-teach", "Nepodarilo sa nájsť prah.")
            return

        thr, tpr, fpr, J = best

        # Zapíš do LSL/USL podľa smeru metriky
        if typ == "diff_from_ref" or (typ.startswith("_wip_edge_") and larger_is_worse):
            # vyššie horšie → USL
            self.dbl_usl.setValue(float(thr))
        else:
            # nižšie horšie → LSL
            self.dbl_lsl.setValue(float(thr))

        QtWidgets.QMessageBox.information(
            self, f"Auto-teach (OK+NOK, {metric_name})",
            f"Prahová hodnota = {thr:.2f}\n"
            f"TPR (zachytenie NOK) = {tpr*100:.1f} %\n"
            f"FPR (falošné OK→NOK) = {fpr*100:.2f} %\n"
            f"J = {J:.3f}\n\n"
            "Klikni „Použiť zmeny“ a potom „Uložiť verziu“."
        )
        
    def _preproc_summary(self, chain):
        if not chain: return "—"
        parts=[]
        for st in chain:
            op = st.get("op","?")
            p  = ", ".join([f"{k}={v}" for k,v in st.items() if k!="op"])
            parts.append(f"{op}({p})" if p else op)
        return " → ".join(parts)

    def open_preproc_dialog(self):
        idx = self.current_tool_idx
        if idx is None or idx < 0:
            QtWidgets.QMessageBox.information(self, "Predspracovanie", "Najprv vyber nástroj v zozname.")
            return
        t = self.recipe.get("tools", [])[idx]
        params = t.setdefault("params", {})
        current = params.get("preproc", []) or []

        dlg = PreprocDialog(self, initial_chain=current)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        chain = dlg.selected_chain()
        params["preproc"] = chain
        self.lbl_preproc.setText(self._preproc_summary(chain))
        QtWidgets.QMessageBox.information(self, "Predspracovanie", "Predspracovanie bolo nastavené pre tento nástroj. Nezabudni „Použiť zmeny…“ a potom „Uložiť verziu“.")
    
    def _view_mode(self) -> str:
        t = getattr(self, "cmb_view", None)
        if not t: return "standard"
        txt = (self.cmb_view.currentText() or "").lower()
        if "čistý" in txt: return "clean"
        if "bez preproc" in txt: return "roi_raw"
        if "po preproc" in txt: return "roi_preproc"
        return "standard"

    def _apply_preproc_chain_preview(self, gray_roi: np.ndarray, chain: list, mask: np.ndarray=None) -> np.ndarray:
        """Mini verzia chain-u len na NÁHĽAD v Builderi (aplikuje sa v ROI, s maskou)."""
        img = gray_roi.copy()
        m = None
        if mask is not None:
            m = mask.copy() if mask.ndim == 2 else cv.cvtColor(mask, cv.COLOR_BGR2GRAY)
            _, m = cv.threshold(m, 1, 255, cv.THRESH_BINARY)
        def blend(tmp):
            if m is None: return tmp
            return np.where(m > 0, tmp, img)
        for st in (chain or []):
            try:
                op = str(st.get("op","")).lower()

                if op == "median":
                    k = int(st.get("k",3)); k = k if k%2==1 else k+1
                    tmp = cv.medianBlur(img, max(1,k)); img = blend(tmp)

                elif op == "gaussian":
                    k = int(st.get("k",3)); k = k if k%2==1 else k+1
                    tmp = cv.GaussianBlur(img, (max(1,k),max(1,k)), 0); img = blend(tmp)

                elif op == "bilateral":
                    d = int(st.get("d",5)); sc=float(st.get("sigmaColor",75.0)); ss=float(st.get("sigmaSpace",75.0))
                    tmp = cv.bilateralFilter(img, max(1,d), sc, ss); img = blend(tmp)

                elif op == "clahe":
                    clip=float(st.get("clip",2.0)); tile=int(st.get("tile",8))
                    clahe = cv.createCLAHE(clipLimit=max(0.1,clip), tileGridSize=(max(1,tile),max(1,tile)))
                    tmp = clahe.apply(img); img = blend(tmp)

                elif op == "tophat":
                    k = int(st.get("k",15)); k = k if k%2==1 else k+1
                    se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k,k))
                    tmp = cv.morphologyEx(img, cv.MORPH_TOPHAT, se); img = blend(tmp)

                elif op == "blackhat":
                    k = int(st.get("k",15)); k = k if k%2==1 else k+1
                    se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k,k))
                    tmp = cv.morphologyEx(img, cv.MORPH_BLACKHAT, se); img = blend(tmp)

                elif op == "unsharp":
                    amt=float(st.get("amount",1.0)); rad=int(st.get("radius",3)); rad = rad if rad%2==1 else rad+1
                    blur = cv.GaussianBlur(img, (max(1,rad),max(1,rad)), 0)
                    tmp = cv.addWeighted(img, 1.0+amt, blur, -amt, 0); img = blend(tmp)

                elif op == "normalize":
                    a=float(st.get("alpha",0.0)); b=float(st.get("beta",255.0))
                    tmp = cv.normalize(img, None, alpha=a, beta=b, norm_type=cv.NORM_MINMAX); img = blend(tmp)

                elif op == "morphgrad":
                    k = int(st.get("k",5)); k = k if k%2==1 else k+1
                    se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (k,k))
                    dil = cv.dilate(img, se); ero = cv.erode(img, se)
                    tmp = cv.subtract(dil, ero); img = blend(tmp)

                elif op == "log":
                    k = int(st.get("k",7)); k = k if k%2==1 else k+1
                    blur = cv.GaussianBlur(img, (k,k), 0)
                    lap  = cv.Laplacian(blur, cv.CV_16S, ksize=3)
                    tmp  = cv.convertScaleAbs(lap); img = blend(tmp)

                elif op == "homo":
                    sigma=float(st.get("sigma",30.0)); gain=float(st.get("gain",1.0))
                    f = img.astype(np.float32)+1.0
                    L = cv.GaussianBlur(f, (0,0), sigmaX=max(0.1,sigma))
                    res = (np.log(f) - np.log(L)) * gain
                    tmp = cv.normalize(res, None, 0, 255, cv.NORM_MINMAX).astype(np.uint8)
                    img = blend(tmp)

                elif op == "retinex":
                    sigma=float(st.get("sigma",25.0))
                    f = img.astype(np.float32)+1.0
                    L = cv.GaussianBlur(f, (0,0), sigmaX=max(0.1,sigma))
                    res = np.log(f) - np.log(L)
                    tmp = cv.normalize(res, None, 0, 255, cv.NORM_MINMAX).astype(np.uint8)
                    img = blend(tmp)

                elif op == "guided":
                    r=int(st.get("r",7)); eps=float(st.get("eps",1e-3))
                    try:
                        gf = cv.ximgproc.guidedFilter(img, img, r, eps)
                        tmp = np.clip(gf,0,255).astype(np.uint8)
                    except Exception:
                        tmp = cv.bilateralFilter(img, d=max(1,r*2+1), sigmaColor=40, sigmaSpace=40)
                    img = blend(tmp)

                elif op == "nlm":
                    h=float(st.get("h",10.0))
                    tmp = cv.fastNlMeansDenoising(img, None, h=h, templateWindowSize=7, searchWindowSize=21)
                    img = blend(tmp)

                elif op == "rollball":
                    r=int(st.get("r",25)); r = r if r%2==1 else r+1
                    se = cv.getStructuringElement(cv.MORPH_ELLIPSE, (r,r))
                    bg = cv.morphologyEx(img, cv.MORPH_OPEN, se)
                    tmp = cv.subtract(img, bg); img = blend(tmp)

                elif op == "sauvola":
                    win=int(st.get("win",25)); win = win if win%2==1 else win+1
                    k=float(st.get("k",0.2))
                    f = img.astype(np.float32)
                    mean = cv.boxFilter(f, ddepth=-1, ksize=(win, win), normalize=True)
                    mean2= cv.boxFilter(f*f, ddepth=-1, ksize=(win, win), normalize=True)
                    var = np.clip(mean2 - mean*mean, 0, None)
                    std = np.sqrt(var); R = 128.0
                    th = mean * (1.0 + k*((std/R)-1.0))
                    tmp = (f > th).astype(np.uint8)*255; img = blend(tmp)

                elif op == "zscore":
                    f = img.astype(np.float32)
                    mu = float(f.mean()); sd = float(f.std()) if f.std()>1e-6 else 1.0
                    z = (f - mu) / sd
                    tmp = cv.normalize(z, None, 0,255, cv.NORM_MINMAX).astype(np.uint8); img = blend(tmp)

                elif op == "clip":
                    lo=float(st.get("lo",5.0)); hi=float(st.get("hi",95.0))
                    lo=max(0.0,min(100.0,lo)); hi=max(lo+0.1,min(100.0,hi))
                    p1,p2 = np.percentile(img,[lo,hi])
                    if p2<=p1: p2=p1+1.0
                    f = np.clip(img.astype(np.float32), p1, p2)
                    tmp = ((f-p1)*(255.0/(p2-p1))).astype(np.uint8); img = blend(tmp)

                elif op == "equalize":
                    tmp = cv.equalizeHist(img); img = blend(tmp)

                elif op == "gabor":
                    angles = st.get("angles",[0,45,90,135]); freq=float(st.get("freq",0.15))
                    lmbd = 1.0/max(1e-6,freq)
                    ksize = int(st.get("ksize",21)); ksize = ksize if ksize%2==1 else ksize+1
                    sigma = float(st.get("sigma", ksize/6.0)); gamma=float(st.get("gamma",0.5))
                    acc=None
                    for a in angles:
                        try:
                            theta=np.deg2rad(float(a))
                            kern=cv.getGaborKernel((ksize,ksize), sigma, theta, lmbd, gamma, 0, ktype=cv.CV_32F)
                            resp=cv.filter2D(img, cv.CV_32F, kern)
                            acc = resp if acc is None else np.maximum(acc, resp)
                        except Exception:
                            continue
                    if acc is not None:
                        tmp = cv.normalize(acc,None,0,255,cv.NORM_MINMAX).astype(np.uint8); img = blend(tmp)

            except Exception:
                continue
        return img        

    def _update_preview_image(self):
        """Prekreslí referenčnú fotku podľa comboboxu „Náhľad“ – bez zmeny súboru na disku."""
        if getattr(self, "ref_img", None) is None:
            return
        base = self.ref_img.copy()
        mode = self._view_mode()

        # vypni/zapni overlay (ROI/masky/shape) v kresliacom widgete
        self.roi_view.set_show_overlays(mode != "clean")

        # ak nie je vybraný nástroj, len zobraz základ
        idx = self.current_tool_idx if self.current_tool_idx is not None else -1
        if idx < 0 or idx >= len(self.recipe.get("tools", [])):
            self.roi_view.set_ndarray(base)
            return

        # --- NOVÝ BLOK (SAFE ROI + CLAMP) ---
        t = self.recipe["tools"][idx]

        # Bezpečné načítanie ROI (ošetrenie None a zlých typov)
        roi_vals = list(t.get("roi_xywh", [0, 0, 0, 0]))
        while len(roi_vals) < 4:
            roi_vals.append(0)

        def as_int(v, default=0):
            try:
                return int(v)
            except Exception:
                return int(default)

        x, y, w, h = (as_int(roi_vals[0]), as_int(roi_vals[1]),
                    as_int(roi_vals[2]), as_int(roi_vals[3]))

        # Orez do hraníc obrázka
        H, W = base.shape[:2]
        x = max(0, min(x, max(0, W-1)))
        y = max(0, min(y, max(0, H-1)))
        w = max(0, min(w, W - x))
        h = max(0, min(h, H - y))

        # Ak ROI nevalídna, len vykresli základ
        if w <= 0 or h <= 0:
            self.roi_view.set_ndarray(base)
            return

        params = t.get("params", {}) or {}
        chain  = params.get("preproc", []) or []

        # Maska vo vnútri ROI (ignorované = 0)
        mask_rects = params.get("mask_rects", []) or []
        m = None
        if mask_rects:
            m = np.full((h, w), 255, np.uint8)
            for rect in mask_rects:
                try:
                    mx,my,mw,mh = [as_int(v, 0) for v in (rect if isinstance(rect, (list, tuple)) else (0,0,0,0))]
                except Exception:
                    continue
                rx = max(0, mx - x); ry = max(0, my - y)
                rw = max(0, min(mw, w - rx)); rh = max(0, min(mh, h - ry))
                if rw > 0 and rh > 0:
                    m[ry:ry+rh, rx:rx+rw] = 0

        if mode == "roi_preproc" and chain:
            roi = base[y:y+h, x:x+w]
            roi_p = self._apply_preproc_chain_preview(roi, chain, mask=m)
            # pre istotu ošetriť tvar
            if isinstance(roi_p, np.ndarray) and roi_p.shape[:2] == (h, w):
                base[y:y+h, x:x+w] = roi_p
            self.roi_view.set_ndarray(base)
        else:
            # "standard", "roi_raw" aj "clean"
            self.roi_view.set_ndarray(base)

