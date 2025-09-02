# app/tabs/run_tab.py
from PyQt5 import QtWidgets, QtCore, QtGui
import cv2 as cv
import numpy as np

from app.widgets.image_view import ImageView
from app.widgets.filmstrip_widget import FilmstripWidget
from qcio.plc.plc_qt_controller import PLCQtController
from storage.dataset_store import save_ok, save_nok

# ak máš mapu PLC, môžeš si sem importnúť konštanty; inak necháme best-effort
try:
    from config.plc_map import CO_READY, CO_BUSY, CO_RESULT_OK, CO_RESULT_NOK
except Exception:
    CO_READY = 0; CO_BUSY = 0; CO_RESULT_OK = 0; CO_RESULT_NOK = 0

def compose_overlay(frame_gray: np.ndarray, out: dict) -> np.ndarray:
    """
    ELI5: Ak fixtúra vrátila H, warpneme celý frame; potom do warpnutej plochy
    „vlepíme“ overlaye jednotlivých nástrojov do ich ROI.
    """
    H_list = out.get("fixture", {}).get("H", None)
    h, w = frame_gray.shape[:2]
    base = cv.cvtColor(frame_gray, cv.COLOR_GRAY2BGR)

    if H_list is not None:
        H = np.array(H_list, dtype=np.float32)
        warped = cv.warpPerspective(base, H, (w, h))
    else:
        warped = base.copy()

    for r in out.get("results", []):
        ov = getattr(r, "overlay", None)
        details = getattr(r, "details", {}) if hasattr(r, "details") else {}
        roi = details.get("roi_xywh", None)
        if ov is None or roi is None:
            continue
        x, y, ww, hh = roi
        x = max(0, min(w-1, x)); y = max(0, min(h-1, y))
        W = min(ww, w - x); Hh = min(hh, h - y)
        if W <= 0 or Hh <= 0:
            continue
        # prispôsob overlay veľkosti výrezu
        try:
            if ov.shape[1] != W or ov.shape[0] != Hh:
                ov = cv.resize(ov, (W, Hh), interpolation=cv.INTER_NEAREST)
            # zľahka zmiešame
            warped[y:y+Hh, x:x+W] = cv.addWeighted(warped[y:y+Hh, x:x+W], 0.6, ov, 0.4, 0)
        except Exception:
            pass

    return warped

class RunTab(QtWidgets.QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._build()

        # interné
        self._last_frame = None
        self._last_out_from_plc = None
        self.plc = None

        # signály
        self.btn_cycle.clicked.connect(self._cycle_now)
        self.btn_trigger.clicked.connect(self._trigger_now)
        self.btn_save_ok.clicked.connect(self._save_ok)
        self.btn_save_nok.clicked.connect(self._save_nok)

        # timer slučka
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.loop_tick)
        self.timer.start(50)  # 20 Hz poll

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()

        # ľavý: obraz
        self.view = ImageView()

        # pravý: ovládanie
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

        self.lbl_last = QtWidgets.QTextEdit()
        self.lbl_last.setReadOnly(True)

        # poskladanie pravého panelu
        right.addWidget(self.lbl_verdict)
        right.addWidget(self.lbl_latency)
        right.addWidget(self.chk_plc)
        right.addWidget(self.lbl_plc)
        right.addWidget(self.btn_cycle)
        right.addWidget(self.btn_trigger)
        right.addWidget(self.btn_save_ok)
        right.addWidget(self.btn_save_nok)
        right.addWidget(QtWidgets.QLabel("Posledné merania:"))
        right.addWidget(self.lbl_last)
        right.addStretch()

        top.addWidget(self.view, 2)
        top.addLayout(right, 1)

        # spodok: filmstrip
        self.film = FilmstripWidget()

        layout.addLayout(top, 5)
        layout.addWidget(self.film, 1)

    def _ensure_plc(self):
        if self.plc is None:
            try:
                self.plc = PLCQtController(host="0.0.0.0", port=5020)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "PLC", f"Modbus server sa nepodarilo spustiť:\n{e}")
                self.chk_plc.setChecked(False)
                self.plc = None

    def _render_out(self, frame_gray, out):
        ok = out.get("ok", True)
        self.lbl_verdict.setText("OK" if ok else "NOK")
        self.lbl_verdict.setStyleSheet(
            "QLabel{font-size:28px; padding:8px; border-radius:8px; background:%s; color:white;}" %
            ("#2e7d32" if ok else "#c62828")
        )
        self.lbl_latency.setText(f"lat: {out.get('elapsed_ms',0.0):.1f} ms")

        comp = compose_overlay(frame_gray, out)
        self.view.set_ndarray(comp)

        lines = []
        for r in out.get("results", []):
            name = getattr(r, "name", "tool")
            measured = getattr(r, "measured", 0.0)
            lsl = getattr(r, "lsl", None)
            usl = getattr(r, "usl", None)
            ok_t = getattr(r, "ok", True)
            lines.append(f"{name} | measured={float(measured):.2f}  LSL={lsl}  USL={usl}  -> {'OK' if ok_t else 'NOK'}")
        self.lbl_last.setPlainText("\n".join(lines))

        # filmstrip thumbnail
        rgb = cv.cvtColor(comp, cv.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QtGui.QImage(rgb.data, w, h, 3*w, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(qimg)
        self.film.add_pixmap(pix)

    def _cycle_now(self):
        """Manuálny single-shot (bez PLC)."""
        if self.state.pipeline is None or self.state.camera is None:
            return
        frm = self.state.get_frame(timeout_ms=150)
        if frm is None:
            return
        self._last_frame = frm.copy()
        out = self.state.process(frm)
        self._render_out(frm, out)

    def _trigger_now(self):
        """Soft PLC test – zdvihneme Coil 20; PLC tick si to spracuje."""
        self._ensure_plc()
        if not self.plc:
            return
        self.plc.mb.set_coil(20, 1)

    def loop_tick(self):
        """Periodický tick – buď PLC mód, alebo voľné spracovanie."""
        if self.state.pipeline is None or self.state.camera is None:
            return

        frm = self.state.get_frame(timeout_ms=50)
        if frm is None:
            return
        self._last_frame = frm.copy()

        if self.chk_plc.isChecked():
            self._ensure_plc()
            if not self.plc:
                return

            # zachytíme výsledok z PLC cyklu (ak nastal)
            self._last_out_from_plc = None
            def do_cycle_capture():
                out = self.state.process(frm)
                self._last_out_from_plc = out
                return out

            self.plc.tick(do_cycle_capture)

            # update PLC stavov (best-effort)
            try:
                ready = self.plc.mb.get_coil(CO_READY)
                busy  = self.plc.mb.get_coil(CO_BUSY)
                rok   = self.plc.mb.get_coil(CO_RESULT_OK)
                rno   = self.plc.mb.get_coil(CO_RESULT_NOK)
                self.lbl_plc.setText(f"PLC: Ready={ready} Busy={busy} OK={rok} NOK={rno}")
            except Exception:
                pass

            # ak prebehol cyklus, vykresli výsledok a stiahni testovací trigger späť
            if self._last_out_from_plc is not None:
                self._render_out(frm, self._last_out_from_plc)
                try:
                    self.plc.mb.set_coil(20, 0)
                except Exception:
                    pass
        else:
            # ne-PLC mód: priebežné spracovanie
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
