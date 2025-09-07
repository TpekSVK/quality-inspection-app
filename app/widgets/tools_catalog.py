# app/widgets/tools_catalog.py
from PyQt5 import QtWidgets, QtCore, QtGui


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

        top_bar = QtWidgets.QHBoxLayout()
        top_bar.addWidget(QtWidgets.QLabel("Nástroje"))
        top_bar.addStretch(1)
        self.edit_search = QtWidgets.QLineEdit()
        self.edit_search.setPlaceholderText("Hľadať nástroj…")
        self.edit_search.setClearButtonEnabled(True)
        top_bar.addWidget(self.edit_search, 0)
        rv.addLayout(top_bar)

        self.list_tools = QtWidgets.QListWidget()
        self.list_tools.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        # režim GRID (kartičky)
        self.list_tools.setViewMode(QtWidgets.QListView.IconMode)
        self.list_tools.setResizeMode(QtWidgets.QListView.Adjust)
        self.list_tools.setWrapping(True)
        self.list_tools.setSpacing(12)
        self.list_tools.setWordWrap(True)
        self.list_tools.setIconSize(QtCore.QSize(56, 56))
        self.list_tools.setUniformItemSizes(False)
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
        def _cat_icon(name: str) -> QtGui.QIcon:
            # malé 24x24
            pm = QtGui.QPixmap(24,24); pm.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            name_l = (name or "").lower()
            if "detek" in name_l:   pen = QtGui.QPen(QtGui.QColor(255,193,7), 3)   # žltá
            elif "zarovn" in name_l or "pozic" in name_l: pen = QtGui.QPen(QtGui.QColor(33,150,243), 3) # modrá
            elif "počít" in name_l: pen = QtGui.QPen(QtGui.QColor(0,200,120), 3)  # zelená
            elif "kód" in name_l or "ocr" in name_l: pen = QtGui.QPen(QtGui.QColor(120,120,255), 3)
            else: pen = QtGui.QPen(QtGui.QColor(150,150,150), 3)
            p.setPen(pen); p.drawRect(4,4,16,16); p.end()
            return QtGui.QIcon(pm)

        self.list_cat.clear()
        for cat in self._categories:
            it = QtWidgets.QListWidgetItem(_cat_icon(cat["title"]), cat["title"])
            it.setData(QtCore.Qt.UserRole, cat)
            self.list_cat.addItem(it)

        # vyber prvú kategóriu, nech nie je currentItem None
        if self.list_cat.count() > 0:
            self.list_cat.setCurrentRow(0)



        # signály
        self.list_cat.currentItemChanged.connect(self._on_cat_changed)
        self.list_tools.currentItemChanged.connect(self._on_tool_changed)
        self.list_tools.itemDoubleClicked.connect(lambda *_: self._on_add())
        self.edit_search.textChanged.connect(self._on_search)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_close.clicked.connect(self.reject)




    # --- verejné API ---
    def selected_template(self):
        """Vracia dict so šablónou nástroja alebo None."""
        return self._selected_tpl

    # --- handlers ---
    def _on_cat_changed(self, cur, prev):
        self._selected_tpl = None
        self.btn_add.setEnabled(False)
        self.list_tools.clear()
        self.desc.clear()
        if not cur:
            return
        cat = cur.data(QtCore.Qt.UserRole)
        self._render_tools_list(cat, self.edit_search.text().strip())
        # kým nie je vybraný tool, ukáž popis kategórie
        cat_desc = cat.get("desc", "")
        if cat_desc:
            self.desc.setPlainText(cat_desc)


    def _on_tool_changed(self, cur, prev):
        self._selected_tpl = None
        self.btn_add.setEnabled(False)
        self.desc.clear()
        if not cur:
            return
        t = cur.data(QtCore.Qt.UserRole)
        self._selected_tpl = t
        txt = t.get("desc","")
        # doplň názov kvôli čitateľnosti
        self.desc.setPlainText(f"{t.get('title','')}\n\n{txt}" if txt else t.get("title",""))
        self.btn_add.setEnabled(t.get("enabled", True))


    def _on_add(self):
        # potvrď výber a zavri dialóg
        self.accept()

    def _make_icon_24(self, painter_fn) -> QtGui.QIcon:
        pm = QtGui.QPixmap(56, 56)   # väčšia ikonka do gridu
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter_fn(p)
        p.end()
        return QtGui.QIcon(pm)

    def _icon_for_tool(self, t: dict) -> QtGui.QIcon:
        typ = t.get("type","")
        # perá (farby ako v appke)
        pen_roi    = QtGui.QPen(QtGui.QColor(33,150,243), 4)    # modrá (ROI/diff)
        pen_mask   = QtGui.QPen(QtGui.QColor(156,39,176), 4)    # fialová (presence)
        pen_detect = QtGui.QPen(QtGui.QColor(0,200,120), 4)     # zelená (detekcie / yolo)
        pen_edge   = QtGui.QPen(QtGui.QColor(255,193,7), 4)     # žltá (edge-trace)

        def ic_diff(p: QtGui.QPainter):
            p.setPen(pen_roi)
            p.drawRect(10, 12, 26, 18)
            p.setPen(QtGui.QPen(QtGui.QColor(255,64,64), 3))
            p.drawLine(14,16,20,22)  # "rozdiely" červené čiarovky
            p.drawLine(20,16,14,22)
            p.drawLine(28,18,34,24)

        def ic_presence(p):
            p.setPen(pen_mask)
            p.drawRect(10, 10, 36, 24)
            p.setPen(QtGui.QPen(QtGui.QColor(0,180,0), 5))
            # fajka
            path = QtGui.QPainterPath()
            path.moveTo(14,26); path.lineTo(22,32); path.lineTo(36,16)
            p.drawPath(path)

        def ic_yolo(p):
            p.setPen(pen_detect)
            p.drawRect(8, 12, 18, 12)
            p.drawRect(30, 18, 16, 10)
            p.setPen(QtGui.QPen(QtGui.QColor(0,180,0), 2))
            p.drawText(12, 38, "YO")

        def ic_line(p):
            p.setPen(pen_edge); p.drawLine(10, 40, 42, 14)

        def ic_circle(p):
            p.setPen(pen_edge); p.drawEllipse(12, 12, 32, 32)

        def ic_curve(p):
            p.setPen(pen_edge)
            path = QtGui.QPainterPath()
            path.moveTo(10, 40); path.cubicTo(18,10, 36,46, 46,16)
            p.drawPath(path)

        # mapovanie type -> ikonka
        if   typ == "diff_from_ref":       return self._make_icon_24(ic_diff)
        elif typ == "presence_absence":    return self._make_icon_24(ic_presence)
        elif typ == "yolo_roi":            return self._make_icon_24(ic_yolo)
        elif typ == "_wip_edge_line":      return self._make_icon_24(ic_line)
        elif typ == "_wip_edge_circle":    return self._make_icon_24(ic_circle)
        elif typ == "_wip_edge_curve":     return self._make_icon_24(ic_curve)
        else:
            # default – neutrálna karta
            def ic_default(p):
                pen = QtGui.QPen(QtGui.QColor(120,120,120), 3)
                p.setPen(pen); p.drawRect(12, 12, 32, 24)
            return self._make_icon_24(ic_default)


    def _render_tools_list(self, cat: dict, query: str):
        """Vyrenderuje kartičky nástrojov danej kategórie podľa filtra."""
        self.list_tools.clear()
        q = (query or "").lower()
        color = QtGui.QColor(255, 193, 7)  # žltý badge default
        for t in cat.get("tools", []):
            title = t.get("title","")
            desc  = t.get("desc","")
            if q and (q not in title.lower() and q not in desc.lower()):
                continue

            # ikonka (jednoduchý farebný štvorček)
            icon = self._icon_for_tool(t)


            label = title + ("" if t.get("enabled", True) else "  (čoskoro)")
            it = QtWidgets.QListWidgetItem(icon, label)
            it.setData(QtCore.Qt.UserRole, t)
            it.setToolTip(desc or title)
            # disabled vizuál
            if not t.get("enabled", True):
                it.setFlags(it.flags() & ~QtCore.Qt.ItemIsEnabled)
            # veľkosť kartičky (text pod ikonou)
            it.setSizeHint(QtCore.QSize(160, 110))
            self.list_tools.addItem(it)

    def _on_search(self, text: str):
        cur = self.list_cat.currentItem()
        if not cur:
            return
        cat = cur.data(QtCore.Qt.UserRole)
        self._render_tools_list(cat, text)
        self._selected_tpl = None
        self.btn_add.setEnabled(False)
        # keď filter zmením, nechám v popise popis kategórie (kým užívateľ znova neklikne na položku)
        self.desc.clear()
        cat_desc = cat.get("desc", "")
        if cat_desc:
            self.desc.setPlainText(cat_desc)


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
                "params":{"canny_lo":40, "canny_hi":120, "metric":"px_gap", "shape":"line","pts":[[10,10],[100,10]],"width":3},
                "units":"px",
                "desc":"Kontrola súvislosti pozdĺž čiary (napr. či hrana nie je prerušená). Potrebuje kreslenie čiary v ROI.",
                "enabled": True
            },
            {
                "id":"defect_on_circle",
                "title":"Vada na kružnici",
                "type":"_wip_edge_circle",
                "params":{"canny_lo":40, "canny_hi":120, "metric":"px_gap", "shape":"circle","cx":80,"cy":80,"r":60,"width":3},
                "units":"px",
                "desc":"Kontrola defektov po obvode. Potrebuje kreslenie kružnice v ROI.",
                "enabled": True
            },
            {
                "id":"defect_on_curve",
                "title":"Vada na krivke",
                "type":"_wip_edge_curve",
                "params":{"canny_lo":40, "canny_hi":120, "metric":"px_gap", "shape":"polyline","pts":[[10,10],[40,30],[90,60]],"width":3},
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
                "type":"blob_count",
                "params":{"mask_rects":[], "min_area":120, "invert":False, "preproc":[]},
                "units":"ks",
                "desc":"Spočíta objekty v ROI po binarizácii (Otsu) a filtrovaní podľa plochy. Rešpektuje masky a predspracovanie.",
                "enabled": True
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
