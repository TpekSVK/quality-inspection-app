# app/widgets/tools_catalog.py
from PyQt5 import QtWidgets, QtCore

class ToolCatalogDialog(QtWidgets.QDialog):
    """
    Katalóg nástrojov v štýle Keyence:
    - vľavo kategórie
    - vpravo zoznam nástrojov v kategórii
    - dole popis + tlačidlo 'Pridať nástroj'

    Vracia 1 zvolený 'template' (dict) alebo None.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Katalóg nástrojov")
        self.resize(900, 600)

        self._selected_tpl = None

        self._categories = self._build_catalog_data()

        # UI
        main = QtWidgets.QVBoxLayout(self)
        splitter = QtWidgets.QSplitter()
        main.addWidget(splitter, 1)

        # vľavo: kategórie
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.addWidget(QtWidgets.QLabel("Kategórie"))
        self.list_cat = QtWidgets.QListWidget()
        lv.addWidget(self.list_cat, 1)
        splitter.addWidget(left)

        # vpravo: nástroje + popis + akcia
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)

        rv.addWidget(QtWidgets.QLabel("Nástroje"))
        self.list_tools = QtWidgets.QListWidget()
        self.list_tools.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        rv.addWidget(self.list_tools, 1)

        self.desc = QtWidgets.QTextEdit()
        self.desc.setReadOnly(True)
        self.desc.setMinimumHeight(140)
        rv.addWidget(self.desc)

        hb = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("Pridať nástroj")
        self.btn_close = QtWidgets.QPushButton("Zavrieť")
        hb.addStretch(1)
        hb.addWidget(self.btn_add)
        hb.addWidget(self.btn_close)
        rv.addLayout(hb)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # naplň kategórie
        for cat in self._categories:
            it = QtWidgets.QListWidgetItem(cat["title"])
            it.setData(QtCore.Qt.UserRole, cat)
            self.list_cat.addItem(it)
        if self.list_cat.count() > 0:
            self.list_cat.setCurrentRow(0)

        # signály
        self.list_cat.currentItemChanged.connect(self._on_cat_changed)
        self.list_tools.currentItemChanged.connect(self._on_tool_changed)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_close.clicked.connect(self.reject)

        self._on_cat_changed(self.list_cat.currentItem(), None)

    # --- verejné API ---
    def selected_template(self):
        """Vracia dict so šablónou nástroja alebo None."""
        return self._selected_tpl

    # --- handlers ---
    def _on_cat_changed(self, cur, prev):
        self.list_tools.clear()
        self.desc.clear()
        self._selected_tpl = None
        if not cur:
            return
        cat = cur.data(QtCore.Qt.UserRole)
        for t in cat["tools"]:
            label = t["title"]
            if not t.get("enabled", True):
                label += "  (čoskoro)"
            it = QtWidgets.QListWidgetItem(label)
            it.setData(QtCore.Qt.UserRole, t)
            if not t.get("enabled", True):
                it.setFlags(it.flags() & ~QtCore.Qt.ItemIsEnabled)
            self.list_tools.addItem(it)
        self.btn_add.setEnabled(False)

    def _on_tool_changed(self, cur, prev):
        self.desc.clear()
        self._selected_tpl = None
        self.btn_add.setEnabled(False)
        if not cur:
            return
        t = cur.data(QtCore.Qt.UserRole)
        self._selected_tpl = t
        self.desc.setPlainText(t.get("desc",""))
        self.btn_add.setEnabled(t.get("enabled", True))

    def _on_add(self):
        # potvrď výber a zavri dialóg
        self.accept()

    # --- dáta katalógu (bezpečne mapované na existujúce tool typy) ---
    def _build_catalog_data(self):
        """
        Každý 'tool template' je dict:
        {
          "id": "defect_area",
          "title": "Celková plocha všetkých vád",
          "type": "diff_from_ref",     # existujúci typ v recepte
          "params": {...},              # default parametre
          "units": "px²",               # units
          "desc": "krátky popis",
          "enabled": True|False         # False = zatiaľ len v náhľade (čoskoro)
        }
        """

        defect_tools = [
            {
                "id":"defect_area",
                "title":"Celková plocha všetkých vád",
                "type":"diff_from_ref",
                "params":{"blur":3, "thresh":35, "morph_open":1, "min_blob_area":120, "measure":"area", "mask_rects":[]},
                "units":"px²",
                "desc":"Porovnanie s referenciou + prahovanie. Výstup: plocha vád v ROI (px²). Vhodné pre škvrny, otrepy, znečistenie.",
                "enabled": True
            },
            {
                "id":"defect_count",
                "title":"Počet vád (bloby)",
                "type":"diff_from_ref",
                "params":{"blur":3, "thresh":40, "morph_open":1, "min_blob_area":120, "measure":"count", "mask_rects":[]},
                "units":"ks",
                "desc":"Porovnanie s referenciou + prahovanie. Výstup: počet vád ako počet blobov.",
                "enabled": True
            },
            {
                "id":"defect_black_white_area",
                "title":"Celková plocha čierna/biela",
                "type":"diff_from_ref",
                "params":{"blur":3, "thresh":45, "morph_open":1, "min_blob_area":150, "measure":"area", "mask_rects":[]},
                "units":"px²",
                "desc":"Variant pre veľmi tmavé/svetlé vady. Východzí prah 45, vhodný na lesklejšie/kontrastné povrchy.",
                "enabled": True
            },
            {
                "id":"defect_vs_background",
                "title":"Vada odlišná od pozadia",
                "type":"diff_from_ref",
                "params":{"blur":5, "thresh":35, "morph_open":1, "min_blob_area":120, "measure":"area", "mask_rects":[]},
                "units":"px²",
                "desc":"Citlivejšie na šum pozadia – mierne väčšie rozmazanie (blur=5) pred porovnaním.",
                "enabled": True
            },
            {
                "id":"yolo_in_roi",
                "title":"YOLO v ROI",
                "type":"yolo_roi",
                "params":{"mask_rects":[]},
                "units":"ks",
                "desc":"Detekcia známych typov chýb alebo cudzích predmetov len v definovaných ROI. Vyžaduje natrénovaný model (ONNX).",
                "enabled": True
            },
            # ---- príprava na nové kreslenia (WIP) ----
            {
                "id":"defect_on_line",
                "title":"Vada na priamke",
                "type":"_wip_edge_line",
                "params":{"shape":"line","pts":[[10,10],[100,10]],"width":3},
                "units":"px",
                "desc":"Kontrola súvislosti pozdĺž čiary (napr. či hrana nie je prerušená). Potrebuje kreslenie čiary v ROI.",
                "enabled": True
            },
            {
                "id":"defect_on_circle",
                "title":"Vada na kružnici",
                "type":"_wip_edge_circle",
                "params":{"shape":"circle","cx":80,"cy":80,"r":60,"width":3},
                "units":"px",
                "desc":"Kontrola defektov po obvode. Potrebuje kreslenie kružnice v ROI.",
                "enabled": True
            },
            {
                "id":"defect_on_curve",
                "title":"Vada na krivke",
                "type":"_wip_edge_curve",
                "params":{"shape":"polyline","pts":[[10,10],[40,30],[90,60]],"width":3},
                "units":"px",
                "desc":"Kontrola pozdĺž ľubovoľnej krivky (polyline). Potrebuje kreslenie lomenej čiary v ROI.",
                "enabled": True
            },

        ]


        presence_tools = [
            {
                "id":"presence_abs",
                "title":"Prítomnosť/Absencia tvaru",
                "type":"presence_absence",
                "params":{"mask_rects":[]},
                "units":"bool",
                "desc":"Overí, či je tvar/otvor/objekt prítomný v ROI (podľa jednoduchých feature/edge pravidiel).",
                "enabled": True
            },
            # ďalšie podtypy (NCC šablóna, SSIM…) môžeme doplniť neskôr
            {
                "id":"template_ncc",
                "title":"Šablóna (NCC) – skóre",
                "type":"_wip_template",
                "params":{},
                "units":"score",
                "desc":"Normalised Cross-Correlation proti menšej šablóne. Čoskoro.",
                "enabled": False
            },
        ]

        measure_tools = [
            {
                "id":"edge_distance",
                "title":"Hrany & vzdialenosť",
                "type":"_wip_edge_distance",
                "params":{},
                "units":"mm",
                "desc":"Zmeria odsadenie medzi dvomi hranami (px→mm). Čoskoro.",
                "enabled": False
            },
            {
                "id":"hough_circle",
                "title":"Otvor/kruh (Hough)",
                "type":"_wip_hough_circle",
                "params":{},
                "units":"mm",
                "desc":"Zistí otvor a priemer v mm, voliteľne kruhovitosť. Čoskoro.",
                "enabled": False
            },
            {
                "id":"blob_count",
                "title":"Počítanie kusov (bloby)",
                "type":"_wip_blob_count",
                "params":{},
                "units":"ks",
                "desc":"Spočíta objekty v ROI po prahovaní. Čoskoro.",
                "enabled": False
            },
        ]

        texture_tools = [
            {
                "id":"ssim_diff",
                "title":"SSIM rozdiel od referencie",
                "type":"_wip_ssim",
                "params":{},
                "units":"score",
                "desc":"Citlivejšie na štruktúru/lesk ako obyčajné prahovanie. Čoskoro.",
                "enabled": False
            },
            {
                "id":"anomaly_texture",
                "title":"Textúra – anomálie (bez NN)",
                "type":"_wip_texture_anom",
                "params":{},
                "units":"score",
                "desc":"LBP/GLCM z OK snímok → odľahlosť. Auto-teach FPR. Čoskoro.",
                "enabled": False
            },
        ]

        codes_tools = [
            {
                "id":"qr_dm_roi",
                "title":"QR/DM kód v ROI",
                "type":"_wip_codes",
                "params":{},
                "units":"text",
                "desc":"Prečíta QR/DataMatrix v ROI; môže prepínať recepty. Čoskoro.",
                "enabled": False
            },
        ]

        return [
            {"id":"defect", "title":"Detekcia vád", "desc":"Klasické CV porovnanie s referenciou a detekcia objektov.", "tools": defect_tools},
            {"id":"presence", "title":"Prítomnosť / Absencia", "desc":"Overenie prítomnosti/otvoru/tvaru.", "tools": presence_tools},
            {"id":"measure", "title":"Merania tvarov", "desc":"Hrany, vzdialenosť, priemer, počet kusov.", "tools": measure_tools},
            {"id":"texture", "title":"Textúra / Anomálie", "desc":"SSIM a štatistické anomálie bez NN.", "tools": texture_tools},
            {"id":"codes", "title":"Kódy a OCR", "desc":"Čiarové/2D kódy, text.", "tools": codes_tools},
        ]
