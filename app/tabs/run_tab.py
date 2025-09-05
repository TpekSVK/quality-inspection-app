# app/tabs/run_tab.py
from PyQt5 import QtWidgets, QtCore, QtGui
import cv2 as cv
import numpy as np

from app.widgets.image_view import ImageView
from app.widgets.filmstrip_widget import FilmstripWidget
from qcio.plc.plc_qt_controller import PLCQtController
from storage.dataset_store import save_ok, save_nok
from storage.recipe_store_json import RecipeStoreJSON

try:
    from config.plc_map import CO_READY, CO_BUSY, CO_RESULT_OK, CO_RESULT_NOK
except Exception:
    CO_READY=CO_BUSY=CO_RESULT_OK=CO_RESULT_NOK=0

def compose_overlay(frame_gray: np.ndarray, ref_shape: tuple, out: dict, only_idx: int = None) -> np.ndarray:
    h_ref, w_ref = ref_shape
    base = frame_gray
    if base.shape[:2] != (h_ref, w_ref):
        base = cv.resize(base, (w_ref, h_ref), interpolation=cv.INTER_LINEAR)
    canvas = cv.cvtColor(base, cv.COLOR_GRAY2BGR)
    for i, r in enumerate(out.get("results", [])):
        if only_idx is not None and i != only_idx:
            continue
        ov = getattr(r, "overlay", None)
        details = getattr(r, "details", {}) if hasattr(r, "details") else {}
        # masky – fialové
        masks = details.get("mask_rects", []) or []
        for (mx,my,mw,mh) in masks:
            x1 = max(0, min(w_ref-1, int(mx)))
            y1 = max(0, min(h_ref-1, int(my)))
            x2 = max(0, min(w_ref,   int(mx+mw)))
            y2 = max(0, min(h_ref,   int(my+mh)))
            if x2 > x1 and y2 > y1:
                cv.rectangle(canvas, (x1,y1), (x2,y2), (255, 0, 255), 2)
        roi = details.get("roi_xywh", None)
        if ov is None or roi is None:
            continue
        x, y, ww, hh = [int(v) for v in roi]
        x = max(0, min(w_ref-1, x)); y = max(0, min(h_ref-1, y))
        W = min(ww, w_ref - x); Hh = min(hh, h_ref - y)
        if W <= 0 or Hh <= 0:
            continue
        try:
            if ov.shape[1] != W or ov.shape[0] != Hh:
                ov = cv.resize(ov, (W, Hh), interpolation=cv.INTER_NEAREST)
            canvas[y:y+Hh, x:x+W] = cv.addWeighted(canvas[y:y+Hh, x:x+W], 0.6, ov, 0.4, 0)
            cv.rectangle(canvas, (x,y), (x+W, y+Hh), (255, 153, 0), 2)
        except Exception:
            pass
    return canvas


class RunTab(QtWidgets.QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        # defaulty ešte PRED prvým populate (aby existovali)
        self._last_frame = None
        self._last_out = None
        self._last_out_from_plc = None
        self._visible_tool_idx = None

        self._build()
        self.tool_strip.currentRowChanged.connect(self._on_tool_selected_from_strip)

        # až teraz – tool_strip už existuje a interné premenne sú definované
        self._populate_tool_strip()



        self._last_frame = None
        self._last_out_from_plc = None
        self.plc = None

        self.btn_cycle.clicked.connect(self._cycle_now)
        self.btn_trigger.clicked.connect(self._trigger_now)
        self.btn_save_ok.clicked.connect(self._save_ok)
        self.btn_save_nok.clicked.connect(self._save_nok)

        # živé ladenie
        self.chk_live.stateChanged.connect(self._on_live_toggle)
        self.btn_live_from_tool.clicked.connect(self._load_live_from_first_tool)
        self.btn_live_reset.clicked.connect(self._reset_live)
        self.btn_live_write.clicked.connect(self._write_live_to_recipe)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.loop_tick)
        self.timer.start(50)

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()

        self.view = ImageView()

        right = QtWidgets.QVBoxLayout()
        self.lbl_verdict = QtWidgets.QLabel("—")
        self.lbl_verdict.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_verdict.setStyleSheet("QLabel{font-size:28px; padding:8px; border-radius:8px; background:#555; color:white;}")

        self.lbl_latency = QtWidgets.QLabel("lat: -- ms")
        self.chk_plc = QtWidgets.QCheckBox("PLC mód (Modbus/TCP)")
        self.lbl_plc = QtWidgets.QLabel("PLC: Ready=0 Busy=0 OK=0 NOK=0")

        self.btn_cycle = QtWidgets.QPushButton("Spustiť 1 cyklus (manuálne)")
        self.btn_trigger = QtWidgets.QPushButton("PLC Test Trigger (coil 20)")
        self.btn_save_ok = QtWidgets.QPushButton("Uložiť OK")
        self.btn_save_nok = QtWidgets.QPushButton("Uložiť NOK")

        # ŽIVÉ LADENIE
        live = QtWidgets.QGroupBox("Živé ladenie (dočasné)")
        f = QtWidgets.QFormLayout(live)
        self.chk_live = QtWidgets.QCheckBox("Aktívne")
        self.spin_live_thresh = QtWidgets.QSpinBox(); self.spin_live_thresh.setRange(0,255); self.spin_live_thresh.setValue(35)
        self.spin_live_morph = QtWidgets.QSpinBox(); self.spin_live_morph.setRange(0,10); self.spin_live_morph.setValue(1)
        self.spin_live_blob  = QtWidgets.QSpinBox(); self.spin_live_blob.setRange(0,100000); self.spin_live_blob.setValue(120)
        self.cmb_live_measure = QtWidgets.QComboBox(); self.cmb_live_measure.addItems(["Plocha vád (px²)", "Počet vád"])
        hb = QtWidgets.QHBoxLayout()
        self.btn_live_from_tool = QtWidgets.QPushButton("Načítať z nástroja")
        self.btn_live_reset = QtWidgets.QPushButton("Reset")
        self.btn_live_write = QtWidgets.QPushButton("Zapísať do receptu")
        hb.addWidget(self.btn_live_from_tool); hb.addWidget(self.btn_live_reset); hb.addWidget(self.btn_live_write)

        f.addRow(self.chk_live)
        f.addRow("Citlivosť – prahovanie", self.spin_live_thresh)
        f.addRow("Čistenie šumu – iterácie", self.spin_live_morph)
        f.addRow("Min. plocha vady [px²]", self.spin_live_blob)
        f.addRow("Metóda merania", self.cmb_live_measure)
        f.addRow(hb)

        self.lbl_last = QtWidgets.QTextEdit(); self.lbl_last.setReadOnly(True)

        right.addWidget(self.lbl_verdict)
        right.addWidget(self.lbl_latency)
        right.addWidget(self.chk_plc)
        right.addWidget(self.lbl_plc)
        right.addWidget(self.btn_cycle)
        right.addWidget(self.btn_trigger)
        right.addWidget(self.btn_save_ok)
        right.addWidget(self.btn_save_nok)
        right.addWidget(live)
        right.addWidget(QtWidgets.QLabel("Posledné merania:"))
        right.addWidget(self.lbl_last)
        right.addStretch()

        top.addWidget(self.view, 2)
        top.addLayout(right, 1)

        self.film = FilmstripWidget()
        # --- TOOL STRIP (náhľady nástrojov) ---
        self.tool_strip = QtWidgets.QListWidget()
        self.tool_strip.setViewMode(QtWidgets.QListView.IconMode)
        self.tool_strip.setFlow(QtWidgets.QListView.LeftToRight)
        self.tool_strip.setWrapping(False)
        self.tool_strip.setResizeMode(QtWidgets.QListView.Adjust)
        self.tool_strip.setIconSize(QtCore.QSize(128, 80))
        self.tool_strip.setSpacing(8)
        self.tool_strip.setFixedHeight(112)
        self.tool_strip.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.tool_strip, 0)

        layout.addLayout(top, 5)
        layout.addWidget(self.film, 1)
        self.tool_strip.currentRowChanged.connect(self._on_tool_selected_from_strip)


    # ---------- PLC ----------
    def _ensure_plc(self):
        if self.plc is None:
            try:
                self.plc = PLCQtController(host="0.0.0.0", port=5020)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "PLC", f"Modbus server sa nepodarilo spustiť:\n{e}")
                self.chk_plc.setChecked(False)
                self.plc = None

    # ---------- Live tuning ----------
    def _on_live_toggle(self, _):
        if self.chk_live.isChecked():
            self._load_live_from_first_tool()

    def _load_live_from_first_tool(self):
        try:
            tools = getattr(self.state.pipeline, "tools", [])
            for t in tools:
                if t.__class__.__name__ == "DiffFromRefTool":
                    p = t.params or {}
                    self.spin_live_thresh.setValue(int(p.get("thresh",35)))
                    self.spin_live_morph.setValue(int(p.get("morph_open",1)))
                    self.spin_live_blob.setValue(int(p.get("min_blob_area",120)))
                    self.cmb_live_measure.setCurrentText("Plocha vád (px²)" if p.get("measure","area")=="area" else "Počet vád")
                    break
        except Exception:
            pass

    def _apply_live_to_tools(self):
        if not self.chk_live.isChecked():
            return
        try:
            tools = getattr(self.state.pipeline, "tools", [])
            for t in tools:
                if t.__class__.__name__ == "DiffFromRefTool":
                    p = t.params or {}
                    p["thresh"] = int(self.spin_live_thresh.value())
                    p["morph_open"] = int(self.spin_live_morph.value())
                    p["min_blob_area"] = int(self.spin_live_blob.value())
                    p["measure"] = "area" if self.cmb_live_measure.currentText().startswith("Plocha") else "count"
                    t.params = p
        except Exception:
            pass

    def _reset_live(self):
        self.chk_live.setChecked(False)

    def _write_live_to_recipe(self):
        """Zapíše aktuálne live parametre do receptu (všetkým diff_from_ref nástrojom) a uloží verziu."""
        try:
            recipe_name = self.state.current_recipe
            if not recipe_name:
                raise RuntimeError("Nie je aktívny recept.")
            store = RecipeStoreJSON()
            rec = store.load(recipe_name)
            for t in rec.get("tools", []):
                if t.get("type") == "diff_from_ref":
                    p = t.setdefault("params",{})
                    p["thresh"] = int(self.spin_live_thresh.value())
                    p["morph_open"] = int(self.spin_live_morph.value())
                    p["min_blob_area"] = int(self.spin_live_blob.value())
                    p["measure"] = "area" if self.cmb_live_measure.currentText().startswith("Plocha") else "count"
            store.save_version(recipe_name, rec)
            QtWidgets.QMessageBox.information(self, "Zapísané", f"Parametre zapísané do receptu {recipe_name}.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Chyba zápisu", str(e))

    # ---------- Render ----------
    def _render_out(self, frame_gray, out):
        ok = out.get("ok", True)
        self.lbl_verdict.setText("OK" if ok else "NOK")
        self.lbl_verdict.setStyleSheet(
            "QLabel{font-size:28px; padding:8px; border-radius:8px; background:%s; color:white;}" %
            ("#2e7d32" if ok else "#c62828")
        )
        self.lbl_latency.setText(f"lat: {out.get('elapsed_ms',0.0):.1f} ms")
        # Ak pipeline už beží a strip je prázdny alebo nepasuje počet položiek, dopopuluj ho
        tools = getattr(self.state.pipeline, "tools", []) or []
        if (self.tool_strip.count() == 0 and len(tools) > 0) or (self.tool_strip.count() != len(tools)):
            self._populate_tool_strip()

        if self.state.ref_img is not None:
            ref_h, ref_w = self.state.ref_img.shape[:2]
        else:
            ref_h, ref_w = frame_gray.shape[:2]
        comp = compose_overlay(frame_gray, (ref_h, ref_w), out, self._visible_tool_idx)

        self.view.set_ndarray(comp)

        lines = []
        for r in out.get("results", []):
            name     = getattr(r, "name", "nástroj")
            measured = getattr(r, "measured", 0.0)
            lsl      = getattr(r, "lsl", None)
            usl      = getattr(r, "usl", None)
            ok_t     = getattr(r, "ok", True)

            # načítaj detaily skôr, aby sme vedeli prípadne prepnúť jednotky
            details  = getattr(r, "details", {}) or {}
            units    = getattr(r, "units", "")

            # override jednotiek pre edge-trace, ak metrika je coverage_pct
            if details.get("metric") == "coverage_pct":
                units = "%"

            units_str = f" {units}" if units else ""
            lines.append(f"{name} | hodnota={float(measured):.2f}{units_str}  LSL={lsl}  USL={usl}  -> {'OK' if ok_t else 'NOK'}")

            # Edge-trace: metrika a štatistiky
            metric = details.get("metric")
            if metric == "coverage_pct":
                cov = details.get("coverage_pct", 0.0)
                edges = details.get("edges_px", 0)
                band = details.get("band_px", 0)
                canny_lo = details.get("canny_lo", None)
                canny_hi = details.get("canny_hi", None)
                lines.append(f"   ↳ metric={metric} | coverage={cov:.1f}%  edges={edges}/{band}  canny={canny_lo}/{canny_hi}")
            elif metric == "px_gap":
                gap = details.get("gap_px", 0)
                edges = details.get("edges_px", 0)
                band = details.get("band_px", 0)
                canny_lo = details.get("canny_lo", None)
                canny_hi = details.get("canny_hi", None)
                lines.append(f"   ↳ metric={metric} | gap_px={gap}  edges={edges}/{band}  canny={canny_lo}/{canny_hi}")

            # diff_from_ref: ak tool poslal tieto polia, ukáž tuning parametre
            if {"measure","thresh","morph_open","min_blob_area"} <= set(details.keys()):
                measure_name = "Plocha vád (px²)" if details.get("measure") == "area" else "Počet vád"
                lines.append(
                    f"   ↳ measure={measure_name}  thresh={details.get('thresh')}  "
                    f"morph={details.get('morph_open')}  min_blob={details.get('min_blob_area')}"
                )

        self.lbl_last.setPlainText("\n".join(lines))



        rgb = cv.cvtColor(comp, cv.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QtGui.QImage(rgb.data, w, h, 3*w, QtGui.QImage.Format_RGB888)
        self.film.add_pixmap(QtGui.QPixmap.fromImage(qimg))
    
    def _populate_tool_strip(self):
        """Vyplní horný pás náhľadmi nástrojov (podľa pipeline)."""
        self.tool_strip.clear()
        tools = getattr(self.state.pipeline, "tools", []) or []
        ref = getattr(self.state, "ref_img", None)
        if ref is None:
            lf = getattr(self, "_last_frame", None)
            ref = lf if lf is not None else np.zeros((240, 320), np.uint8)



        for i, t in enumerate(tools):
            icon = self._make_tool_icon(ref, t, ok=None, selected=(i == 0))
            it = QtWidgets.QListWidgetItem(icon, getattr(t, "name", f"Tool {i+1}"))
            it.setData(QtCore.Qt.UserRole, i)
            self.tool_strip.addItem(it)

        # default vyber prvý tool, ak existuje
        if self.tool_strip.count() > 0:
            self.tool_strip.setCurrentRow(0)
            self._visible_tool_idx = 0
        else:
            self._visible_tool_idx = None

    def _on_tool_selected_from_strip(self, row: int):
        """Klik na náhľad – zobraz overlay len pre daný tool."""
        if row is None or row < 0:
            self._visible_tool_idx = None
        else:
            self._visible_tool_idx = int(row)

        # re-render posledný frame s posledným out (nečakáme na ďalší tick)
        if self._last_frame is not None and self._last_out is not None:
            self._render_out(self._last_frame, self._last_out)
        # Ak stále nie je nič vybraté, a strip má položky, vyber prvú
        if (self._visible_tool_idx is None) and (self.tool_strip.count() > 0):
            self.tool_strip.setCurrentRow(0)
            self._visible_tool_idx = 0

    def _update_tool_strip_status(self, out: dict):
        """Podľa výsledkov nastav zelený/červený pásik v náhľadoch."""
        tools = getattr(self.state.pipeline, "tools", []) or []
        # ak počet položiek v stripe nepasuje, najprv ho postav znova
        if self.tool_strip.count() != len(tools):
            self._populate_tool_strip()

        ref = getattr(self.state, "ref_img", None)
        if ref is None:
            ref = self._last_frame if self._last_frame is not None else np.zeros((240, 320), np.uint8)

        res = out.get("results", [])
        n = min(len(tools), len(res))
        for i in range(len(tools)):
            ok_flag = None
            if i < n:
                ok_flag = bool(getattr(res[i], "ok", True))
            it = self.tool_strip.item(i)
            if it is None:
                continue
            icon = self._make_tool_icon(ref, tools[i], ok=ok_flag, selected=(i == self._visible_tool_idx))
            it.setIcon(icon)

    def _make_tool_icon(self, ref_gray: np.ndarray, tool, ok: bool = None, selected: bool = False) -> QtGui.QIcon:
        """Vygeneruje QIcon náhľadu: ref obrázok + ROI + (ak je) shape + zelený/červený pásik."""
        try:
            h, w = ref_gray.shape[:2]
        except Exception:
            ref_gray = np.zeros((240,320), np.uint8)
            h, w = ref_gray.shape[:2]

        TW, TH = 128, 80
        small = cv.resize(ref_gray, (TW, TH), interpolation=cv.INTER_AREA)
        bgr = cv.cvtColor(small, cv.COLOR_GRAY2BGR)

        # škálovanie globálnych súradníc do thumbu
        sx = TW / float(w if w else 1)
        sy = TH / float(h if h else 1)

        # ROI (oranžový rámik)
        try:
            x, y, ww, hh = [int(v) for v in getattr(tool, "roi_xywh", (0,0,0,0))]
            x1, y1 = int(x*sx), int(y*sy)
            x2, y2 = int((x+ww)*sx), int((y+hh)*sy)
            cv.rectangle(bgr, (x1,y1), (x2,y2), (0, 200, 255), 2)
        except Exception:
            pass

        # Edge-shape (žltá)
        try:
            p = getattr(tool, "params", {}) or {}
            shape = p.get("shape", None)
            if shape == "line":
                pts = p.get("pts", [])
                if len(pts) == 2:
                    (x1,y1),(x2,y2) = pts
                    cv.line(bgr, (int(x1*sx),int(y1*sy)), (int(x2*sx),int(y2*sy)), (0, 220, 255), 2, cv.LINE_AA)
            elif shape == "circle":
                cx, cy, r = p.get("cx"), p.get("cy"), int(p.get("r", 0))
                if cx is not None and cy is not None and r > 0:
                    cv.circle(bgr, (int(cx*sx), int(cy*sy)), max(1,int(r*sx)), (0, 220, 255), 2, cv.LINE_AA)
            elif shape == "polyline":
                pts = p.get("pts", [])
                if len(pts) >= 2:
                    arr = np.array([[int(px*sx), int(py*sy)] for (px,py) in pts], dtype=np.int32)
                    cv.polylines(bgr, [arr], False, (0, 220, 255), 2, lineType=cv.LINE_AA)
        except Exception:
            pass

        # OK/NOK pásik dole
        if ok is not None:
            color = (0, 170, 0) if ok else (0, 0, 200)
            cv.rectangle(bgr, (0, TH-6), (TW, TH), color, thickness=-1)

        # Výber – žltý okraj
        if selected:
            cv.rectangle(bgr, (1,1), (TW-2, TH-2), (255, 210, 0), 2)

        rgb = cv.cvtColor(bgr, cv.COLOR_BGR2RGB)
        qimg = QtGui.QImage(rgb.data, TW, TH, 3*TW, QtGui.QImage.Format_RGB888)
        return QtGui.QIcon(QtGui.QPixmap.fromImage(qimg))

    # ---------- Cyklus ----------
    def _cycle_now(self):
        if self.state.pipeline is None or self.state.camera is None:
            return
        frm = self.state.get_frame(timeout_ms=150)
        if frm is None: return
        self._last_frame = frm.copy()
        self._apply_live_to_tools()
        out = self.state.process(frm)
        self._render_out(frm, out)
        self._last_out = out
        self._update_tool_strip_status(out)


    def _trigger_now(self):
        self._ensure_plc()
        if not self.plc: return
        self.plc.mb.set_coil(20, 1)

    def loop_tick(self):
        if self.state.pipeline is None or self.state.camera is None:
            return
        frm = self.state.get_frame(timeout_ms=50)
        if frm is None: return
        self._last_frame = frm.copy()

        if self.chk_plc.isChecked():
            self._ensure_plc()
            if not self.plc: return
            self._last_out_from_plc = None
            def do_cycle_capture():
                self._apply_live_to_tools()
                out = self.state.process(frm)
                self._last_out_from_plc = out
                return out
            self.plc.tick(do_cycle_capture)
            if self._last_out_from_plc is not None:
                self._render_out(frm, self._last_out_from_plc)
                self._last_out = self._last_out_from_plc
                self._update_tool_strip_status(self._last_out_from_plc)


                try: self.plc.mb.set_coil(20, 0)
                except: pass
        else:
            self._apply_live_to_tools()
            out = self.state.process(frm)
            self._render_out(frm, out)
            self._last_out = out
            self._update_tool_strip_status(out)


    # --- ukladanie datasetu ---
    def _save_ok(self):
        if self._last_frame is None or self.state.current_recipe is None:
            return
        p = save_ok(self.state.current_recipe, self._last_frame)
        QtWidgets.QMessageBox.information(self, "OK uložené", p)

    def _save_nok(self):
        if self._last_frame is None or self.state.current_recipe is None:
            return
        p = save_nok(self.state.current_recipe, self._last_frame)
        QtWidgets.QMessageBox.information(self, "NOK uložené", p)
