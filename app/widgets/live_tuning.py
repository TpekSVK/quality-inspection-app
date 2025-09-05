from PyQt5 import QtWidgets, QtCore

class LiveTuningPanel(QtWidgets.QGroupBox):
    """
    Kontextové Živé ladenie pre nástroje (diff/edge/presence/yolo).
    - paramsChanged: emituje sa pri zmene ovládacieho prvku
    - loadClicked/resetClicked/saveClicked: forward tlačidiel
    """
    paramsChanged = QtCore.pyqtSignal()
    loadClicked   = QtCore.pyqtSignal()
    resetClicked  = QtCore.pyqtSignal()
    saveClicked   = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Živé ladenie (dočasné)", parent)

        live_v = QtWidgets.QVBoxLayout(self)

        # ON/OFF
        row_on = QtWidgets.QHBoxLayout()
        self.chk_active = QtWidgets.QCheckBox("Aktívne")
        self.chk_active.setChecked(True)
        row_on.addWidget(self.chk_active); row_on.addStretch(1)
        live_v.addLayout(row_on)

        # --- DIFF ---
        self.diff = QtWidgets.QWidget()
        fd = QtWidgets.QFormLayout(self.diff)
        self.diff_thresh = QtWidgets.QSpinBox(); self.diff_thresh.setRange(0,255)
        self.diff_morph  = QtWidgets.QSpinBox(); self.diff_morph.setRange(0,10)
        self.diff_blob   = QtWidgets.QSpinBox(); self.diff_blob.setRange(0, 10_000_000)
        self.diff_measure= QtWidgets.QComboBox(); self.diff_measure.addItems(["Plocha vád (px²)", "Počet vád"])
        fd.addRow("Citlivosť (prahovanie):", self.diff_thresh)
        fd.addRow("Čistenie šumu (morf. open):", self.diff_morph)
        fd.addRow("Min. plocha defektu (px²):", self.diff_blob)
        fd.addRow("Metóda merania:", self.diff_measure)

        # --- EDGE ---
        self.edge = QtWidgets.QWidget()
        fe = QtWidgets.QFormLayout(self.edge)
        self.edge_canny_lo = QtWidgets.QSpinBox(); self.edge_canny_lo.setRange(0,255)
        self.edge_canny_hi = QtWidgets.QSpinBox(); self.edge_canny_hi.setRange(0,255)
        self.edge_width    = QtWidgets.QSpinBox(); self.edge_width.setRange(1,50)
        self.edge_metric   = QtWidgets.QComboBox(); self.edge_metric.addItems(["px_gap (menej=lepšie)", "coverage_pct (viac=lepšie)"])
        fe.addRow("Canny low:", self.edge_canny_lo)
        fe.addRow("Canny high:", self.edge_canny_hi)
        fe.addRow("Šírka profilu:", self.edge_width)
        fe.addRow("Metrika:", self.edge_metric)

        # --- PRESENCE ---
        self.presence = QtWidgets.QWidget()
        fp = QtWidgets.QFormLayout(self.presence)
        self.pres_minScore = QtWidgets.QDoubleSpinBox(); self.pres_minScore.setRange(0.0,1.0); self.pres_minScore.setSingleStep(0.01); self.pres_minScore.setDecimals(3)
        fp.addRow("Min. skóre:", self.pres_minScore)

        # --- YOLO ---
        self.yolo = QtWidgets.QWidget()
        fy = QtWidgets.QFormLayout(self.yolo)
        self.yolo_conf = QtWidgets.QDoubleSpinBox(); self.yolo_conf.setRange(0.0,1.0); self.yolo_conf.setSingleStep(0.01)
        self.yolo_iou  = QtWidgets.QDoubleSpinBox(); self.yolo_iou.setRange(0.0,1.0);  self.yolo_iou.setSingleStep(0.01)
        self.yolo_maxd = QtWidgets.QSpinBox(); self.yolo_maxd.setRange(1, 2000)
        fy.addRow("Conf threshold:", self.yolo_conf)
        fy.addRow("IoU threshold:", self.yolo_iou)
        fy.addRow("Max detections:", self.yolo_maxd)

        # vlož skupiny (default skryté) – ukážeme podľa typu
        for grp in (self.diff, self.edge, self.presence, self.yolo):
            grp.hide()
            live_v.addWidget(grp)

        # Tlačidlá
        row_btn = QtWidgets.QHBoxLayout()
        self.btn_load  = QtWidgets.QPushButton("Načítať z nástroja")
        self.btn_reset = QtWidgets.QPushButton("Reset")
        self.btn_save  = QtWidgets.QPushButton("Zapísať do receptu")
        row_btn.addWidget(self.btn_load); row_btn.addWidget(self.btn_reset)
        row_btn.addStretch(1); row_btn.addWidget(self.btn_save)
        live_v.addLayout(row_btn)

        # forward signálov tlačidiel
        self.btn_load.clicked.connect(self.loadClicked.emit)
        self.btn_reset.clicked.connect(self.resetClicked.emit)
        self.btn_save.clicked.connect(self.saveClicked.emit)

        # emisia paramsChanged pri zmene hodnoty
        def bind_changes(w):
            if hasattr(w, "valueChanged"):
                w.valueChanged.connect(self.paramsChanged.emit)
            if hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(self.paramsChanged.emit)
        for w in (self.diff_thresh, self.diff_morph, self.diff_blob, self.diff_measure,
                  self.edge_canny_lo, self.edge_canny_hi, self.edge_width, self.edge_metric,
                  self.pres_minScore,
                  self.yolo_conf, self.yolo_iou, self.yolo_maxd):
            bind_changes(w)

    # --- verejné API ---
    def is_active(self) -> bool:
        return self.chk_active.isChecked()

    def show_for_type(self, typ: str):
        for grp in (self.diff, self.edge, self.presence, self.yolo):
            grp.hide()
        if typ == "diff_from_ref":
            self.diff.show()
        elif typ in {"_wip_edge_line","_wip_edge_circle","_wip_edge_curve"}:
            self.edge.show()
        elif typ == "presence_absence":
            self.presence.show()
        elif typ == "yolo_roi":
            self.yolo.show()

    def fill_from_tool(self, tool):
        """Načíta hodnoty z tool.params do UI podľa typu toolu."""
        if tool is None: return
        p = dict(getattr(tool, "params", {}) or {})
        typ = (getattr(tool, "type", "") or "").lower()
        # fallback – ak type chýba, skús podľa polí
        if not typ:
            keys = set(p.keys())
            if {"canny_lo","canny_hi","width"} & keys: typ = "_wip_edge_line"
            elif {"minScore"} & keys: typ = "presence_absence"
            elif {"conf_thres","iou_thres","max_det"} & keys: typ = "yolo_roi"
            else: typ = "diff_from_ref"
        self.show_for_type(typ)

        if typ == "diff_from_ref":
            self.diff_thresh.setValue(int(p.get("thresh", 35)))
            self.diff_morph.setValue(int(p.get("morph_open", 1)))
            self.diff_blob.setValue(int(p.get("min_blob_area", 120)))
            self.diff_measure.setCurrentText("Plocha vád (px²)" if p.get("measure","area")=="area" else "Počet vád")
        elif typ in {"_wip_edge_line","_wip_edge_circle","_wip_edge_curve"}:
            self.edge_canny_lo.setValue(int(p.get("canny_lo", 40)))
            self.edge_canny_hi.setValue(int(p.get("canny_hi", 120)))
            self.edge_width.setValue(int(p.get("width", 3)))
            self.edge_metric.setCurrentText("coverage_pct (viac=lepšie)" if str(p.get("metric","px_gap")).lower()=="coverage_pct" else "px_gap (menej=lepšie)")
        elif typ == "presence_absence":
            self.pres_minScore.setValue(float(p.get("minScore", 0.70)))
        elif typ == "yolo_roi":
            self.yolo_conf.setValue(float(p.get("conf_thres", 0.25)))
            self.yolo_iou.setValue(float(p.get("iou_thres", 0.45)))
            self.yolo_maxd.setValue(int(p.get("max_det", 100)))

    def apply_to_tool(self, tool):
        """Zapíše hodnoty z UI do tool.params (len ak panel je Aktívny)."""
        if tool is None or not self.is_active():
            return
        p = dict(getattr(tool, "params", {}) or {})
        typ = (getattr(tool, "type", "") or "").lower()
        if not typ:
            keys = set(p.keys())
            if {"canny_lo","canny_hi","width"} & keys: typ = "_wip_edge_line"
            elif {"minScore"} & keys: typ = "presence_absence"
            elif {"conf_thres","iou_thres","max_det"} & keys: typ = "yolo_roi"
            else: typ = "diff_from_ref"

        if typ == "diff_from_ref":
            p["thresh"]      = int(self.diff_thresh.value())
            p["morph_open"]  = int(self.diff_morph.value())
            p["min_blob_area"]= int(self.diff_blob.value())
            p["measure"]     = "area" if self.diff_measure.currentText().startswith("Plocha") else "count"
        elif typ in {"_wip_edge_line","_wip_edge_circle","_wip_edge_curve"}:
            p["canny_lo"] = int(self.edge_canny_lo.value())
            p["canny_hi"] = int(self.edge_canny_hi.value())
            p["width"]    = int(self.edge_width.value())
            p["metric"]   = "coverage_pct" if self.edge_metric.currentText().startswith("coverage") else "px_gap"
        elif typ == "presence_absence":
            p["minScore"] = float(self.pres_minScore.value())
        elif typ == "yolo_roi":
            p["conf_thres"] = float(self.yolo_conf.value())
            p["iou_thres"]  = float(self.yolo_iou.value())
            p["max_det"]    = int(self.yolo_maxd.value())

        tool.params = p
