# app/widgets/tool_strip.py
from typing import List, Optional
import numpy as np
import cv2 as cv
from PyQt5 import QtWidgets, QtCore, QtGui

class ToolStrip(QtWidgets.QListWidget):
    """
    Horný pás nástrojov ako náhľady (ref/last_frame + ROI + shape + OK/NOK pásik).
    API:
      - set_tools(tools, ref_img, last_frame=None, selected_idx=0)
      - set_tools_if_needed(tools, ref_img, last_frame=None)
      - update_status(out, ref_img, last_frame=None)
      - enable_keyboard(parent)  # ← → a čísla 1..9
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QtWidgets.QListView.IconMode)
        self.setFlow(QtWidgets.QListView.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QtWidgets.QListView.Adjust)
        self.setIconSize(QtCore.QSize(128, 80))
        self.setSpacing(8)
        self.setFixedHeight(112)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        self._tools: List[object] = []
        self._ref_img: Optional[np.ndarray] = None
        self._last_frame: Optional[np.ndarray] = None

    # ---------- public ----------
    def set_tools(self, tools: List[object], ref_img: Optional[np.ndarray], last_frame: Optional[np.ndarray] = None, selected_idx: int = 0):
        self._tools = tools or []
        self._ref_img = ref_img
        self._last_frame = last_frame
        self.clear()
        base = self._pick_base()
        for i, t in enumerate(self._tools):
            icon = self._make_icon(base, t, ok=None, selected=(i == selected_idx))
            it = QtWidgets.QListWidgetItem(icon, getattr(t, "name", f"Tool {i+1}"))
            it.setData(QtCore.Qt.UserRole, i)
            self.addItem(it)
        if self.count() > 0:
            self.setCurrentRow(max(0, min(self.count()-1, selected_idx)))

    def set_tools_if_needed(self, tools: List[object], ref_img: Optional[np.ndarray], last_frame: Optional[np.ndarray] = None):
        if self.count() != len(tools or []):
            self.set_tools(tools, ref_img, last_frame, selected_idx=max(0, self.currentRow()))
        else:
            # aktualizuj base obrázok – bez 'or' na numpy
            if ref_img is not None:
                self._ref_img = ref_img
            if last_frame is not None:
                self._last_frame = last_frame


    def update_status(self, out: dict, ref_img: Optional[np.ndarray] = None, last_frame: Optional[np.ndarray] = None):
        # uložiť nové „base“
        if ref_img is not None:
            self._ref_img = ref_img
        if last_frame is not None:
            self._last_frame = last_frame

        base = self._pick_base()
        res = out.get("results", []) if isinstance(out, dict) else []
        for i in range(self.count()):
            it = self.item(i)
            ok_flag = None
            if i < len(res):
                ok_flag = bool(getattr(res[i], "ok", True))
            icon = self._make_icon(base, self._tools[i] if i < len(self._tools) else None,
                                   ok=ok_flag, selected=(i == self.currentRow()))
            it.setIcon(icon)
            # tooltip (hodnota, limity, metrika)
            tip = self._build_tooltip(i, res)
            it.setToolTip(tip)

    def enable_keyboard(self, parent):
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Left),  parent,
                            activated=lambda: self._move(-1))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Right), parent,
                            activated=lambda: self._move(+1))
        # čísla 1..9
        for k in range(1,10):
            QtWidgets.QShortcut(QtGui.QKeySequence(str(k)), parent,
                                activated=lambda kk=k: self._select_index(kk-1))

    # ---------- internal ----------
    def _move(self, delta: int):
        if self.count() == 0: return
        cur = self.currentRow()
        new = max(0, min(self.count()-1, cur + int(delta)))
        if new != cur:
            self.setCurrentRow(new)

    def _select_index(self, idx: int):
        if 0 <= idx < self.count():
            self.setCurrentRow(idx)

    def _pick_base(self) -> np.ndarray:
        base = self._ref_img
        if base is None:
            base = self._last_frame
        if base is None:
            base = np.zeros((240, 320), np.uint8)
        if base.ndim == 3:
            base = cv.cvtColor(base, cv.COLOR_BGR2GRAY)
        return base

    def _make_icon(self, ref_gray: np.ndarray, tool, ok: bool = None, selected: bool = False) -> QtGui.QIcon:
        try:
            h, w = ref_gray.shape[:2]
        except Exception:
            ref_gray = np.zeros((240,320), np.uint8)
            h, w = ref_gray.shape[:2]

        TW, TH = 128, 80
        small = cv.resize(ref_gray, (TW, TH), interpolation=cv.INTER_AREA)
        bgr = cv.cvtColor(small, cv.COLOR_GRAY2BGR)

        # škálovanie
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

        # Edge shape (žltá)
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

        # OK/NOK pásik
        if ok is not None:
            color = (0, 170, 0) if ok else (0, 0, 200)
            cv.rectangle(bgr, (0, TH-6), (TW, TH), color, thickness=-1)

        # výber – žltý okraj
        if selected:
            cv.rectangle(bgr, (1,1), (TW-2, TH-2), (255, 210, 0), 2)

        rgb = cv.cvtColor(bgr, cv.COLOR_BGR2RGB)
        qimg = QtGui.QImage(rgb.data, TW, TH, 3*TW, QtGui.QImage.Format_RGB888)
        return QtGui.QIcon(QtGui.QPixmap.fromImage(qimg))

    def _build_tooltip(self, i: int, res: list) -> str:
        label = getattr(self._tools[i], "name", f"Tool {i+1}") if i < len(self._tools) else f"Tool {i+1}"
        parts = [label]
        if i < len(res):
            r = res[i]
            measured = getattr(r, "measured", None)
            units    = getattr(r, "units", "") or ""
            lsl      = getattr(r, "lsl", None)
            usl      = getattr(r, "usl", None)
            details  = getattr(r, "details", {}) or {}
            metric   = details.get("metric", None)
            if measured is not None:
                units_str = f" {units}" if units else ""
                parts.append(f"hodnota = {float(measured):.2f}{units_str}")
            parts.append(f"LSL = {lsl}   USL = {usl}")
            if metric == "coverage_pct":
                cov = details.get("coverage_pct", 0.0)
                edges = details.get("edges_px", 0); band = details.get("band_px", 0)
                cl = details.get("canny_lo", None); ch = details.get("canny_hi", None)
                parts += [ "metric = coverage_pct",
                           f"coverage = {cov:.1f}%  edges = {edges}/{band}",
                           f"canny = {cl}/{ch}" ]
            elif metric == "px_gap":
                gap = details.get("gap_px", 0)
                edges = details.get("edges_px", 0); band = details.get("band_px", 0)
                cl = details.get("canny_lo", None); ch = details.get("canny_hi", None)
                parts += [ "metric = px_gap",
                           f"gap_px = {gap}  edges = {edges}/{band}",
                           f"canny = {cl}/{ch}" ]
        return "\n".join(parts)
