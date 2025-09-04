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

def compose_overlay(frame_gray: np.ndarray, ref_shape: tuple, out: dict) -> np.ndarray:
    h_ref, w_ref = ref_shape
    base = frame_gray
    if base.shape[:2] != (h_ref, w_ref):
        base = cv.resize(base, (w_ref, h_ref), interpolation=cv.INTER_LINEAR)
    canvas = cv.cvtColor(base, cv.COLOR_GRAY2BGR)
    for r in out.get("results", []):
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
            cv.rectangle(canvas, (x,y), (x+W, y+Hh), (255, 153, 0), 2)  # modrá-ish
        except Exception:
            pass
    return canvas

class RunTab(QtWidgets.QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._build()

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
        layout.addLayout(top, 5)
        layout.addWidget(self.film, 1)

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

        if self.state.ref_img is not None:
            ref_h, ref_w = self.state.ref_img.shape[:2]
        else:
            ref_h, ref_w = frame_gray.shape[:2]
        comp = compose_overlay(frame_gray, (ref_h, ref_w), out)
        self.view.set_ndarray(comp)

        lines = []
        for r in out.get("results", []):
            name = getattr(r, "name", "nástroj")
            measured = getattr(r, "measured", 0.0)
            lsl = getattr(r, "lsl", None)
            usl = getattr(r, "usl", None)
            ok_t = getattr(r, "ok", True)
            lines.append(f"{name} | hodnota={float(measured):.2f}  LSL={lsl}  USL={usl}  -> {'OK' if ok_t else 'NOK'}")
        self.lbl_last.setPlainText("\n".join(lines))

        rgb = cv.cvtColor(comp, cv.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QtGui.QImage(rgb.data, w, h, 3*w, QtGui.QImage.Format_RGB888)
        self.film.add_pixmap(QtGui.QPixmap.fromImage(qimg))

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
                try: self.plc.mb.set_coil(20, 0)
                except: pass
        else:
            self._apply_live_to_tools()
            out = self.state.process(frm)
            self._render_out(frm, out)

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
