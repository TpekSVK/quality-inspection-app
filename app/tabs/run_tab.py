# app/tabs/run_tab.py
from PyQt5 import QtWidgets, QtCore, QtGui
import cv2 as cv, json, numpy as np
from app.widgets.image_view import ImageView
from app.widgets.filmstrip_widget import FilmstripWidget
from io.plc.plc_qt_controller import PLCQtController
from config.plc_map import *

def compose_overlay(frame_gray: np.ndarray, out: dict) -> np.ndarray:
    """
    ELI5: Ak máme H (fixtúra), warpneme frame -> vložíme overlay ROI každého toolu do tejto warpnutej plochy.
    Keď H nie je, vkladáme overlay priamo do pôvodného frame na ROI súradniciach.
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
        if ov is None: continue
        roi = r.details.get("roi_xywh", None) if hasattr(r, "details") else None
        if roi is None: continue
        x,y,ww,hh = roi
        # bezpečnostné ohraničenie
        x = max(0, min(w-1, x)); y = max(0, min(h-1, y))
        W = min(ww, w-x); Hh = min(hh, h-y)
        try:
            resized = cv.resize(ov, (W, Hh), interpolation=cv.INTER_NEAREST) if (ov.shape[1]!=W or ov.shape[0]!=Hh) else ov
            warped[y:y+Hh, x:x+W] = cv.addWeighted(warped[y:y+Hh, x:x+W], 0.6, resized, 0.4, 0)
        except: pass

    return warped

class RunTab(QtWidgets.QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._build()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.loop_tick)
        self.timer.start(50)  # 20 Hz poll PLC/stream

        self.plc = None  # PLCQtController (lazy)

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

        self.lbl_last = QtWidgets.QTextEdit(); self.lbl_last.setReadOnly(True)

        right.addWidget(self.lbl_verdict)
        right.addWidget(self.lbl_latency)
        right.addWidget(self.chk_plc)
        right.addWidget(self.lbl_plc)
        right.addWidget(QtWidgets.QLabel("Posledné merania:"))
        right.addWidget(self.lbl_last)
        right.addStretch()

        top.addWidget(self.view, 2)
        top.addLayout(right, 1)

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

    def _one_process(self, frame_gray):
        out = self.state.process(frame_gray)
        ok = out["ok"]
        self.lbl_verdict.setText("OK" if ok else "NOK")
        self.lbl_verdict.setStyleSheet(
            "QLabel{font-size:28px; padding:8px; border-radius:8px; background:%s; color:white;}" %
            ("#2e7d32" if ok else "#c62828")
        )
        self.lbl_latency.setText(f"lat: {out['elapsed_ms']:.1f} ms")

        comp = compose_overlay(frame_gray, out)
        self.view.set_ndarray(comp)

        lines = []
        for r in out["results"]:
            name = getattr(r, "name", "tool")
            measured = getattr(r, "measured", 0.0)
            lsl = getattr(r, "lsl", None)
            usl = getattr(r, "usl", None)
            ok_t = getattr(r, "ok", True)
            lines.append(f"{name} | measured={float(measured):.2f}  LSL={lsl}  USL={usl}  -> {'OK' if ok_t else 'NOK'}")
        self.lbl_last.setPlainText("\n".join(lines))

        # filmstrip thumbnail
        rgb = cv.cvtColor(comp, cv.COLOR_BGR2RGB)
        h,w = rgb.shape[:2]
        qimg = QtGui.QImage(rgb.data, w, h, 3*w, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(qimg)
        self.film.add_pixmap(pix)
        return out

    def loop_tick(self):
        # Potrebujeme pipeline a kameru
        if self.state.pipeline is None or self.state.camera is None:
            return

        # načítaj frame
        frm = self.state.get_frame(timeout_ms=50)
        if frm is None:
            return

        if self.chk_plc.isChecked():
            self._ensure_plc()
            if self.plc:
                # nech PLC riadi cyklus (spracuje iba na trigger edge)
                def do_cycle():
                    return self._one_process(frm)
                self.plc.tick(do_cycle)
                # update PLC label (light mirror)
                try:
                    ready = self.plc.mb.get_coil(CO_READY)
                    busy  = self.plc.mb.get_coil(CO_BUSY)
                    rok   = self.plc.mb.get_coil(CO_RESULT_OK)
                    rno   = self.plc.mb.get_coil(CO_RESULT_NOK)
                    self.lbl_plc.setText(f"PLC: Ready={ready} Busy={busy} OK={rok} NOK={rno}")
                except:
                    pass
        else:
            # soft-run stále dookola
            self._one_process(frm)
