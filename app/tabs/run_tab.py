# app/tabs/run_tab.py
from PyQt5 import QtWidgets, QtCore, QtGui
import cv2 as cv
import numpy as np

from app.widgets.image_view import ImageView
from app.widgets.filmstrip_widget import FilmstripWidget
from app.widgets.tool_strip import ToolStrip
from core.vis.overlay import compose_overlay

from app.widgets.live_tuning import LiveTuningPanel
from qcio.plc.plc_qt_controller import PLCQtController
from storage.dataset_store import save_ok, save_nok
from storage.recipe_store_json import RecipeStoreJSON
# Robustné rozpoznanie typu nástroja v RUN (pre Live tuning)
try:
    from core.tools.diff_from_ref import DiffFromRefTool
except Exception:
    DiffFromRefTool = None

try:
    from core.tools.edge_trace import EdgeTraceLineTool, EdgeTraceCircleTool, EdgeTraceCurveTool
except Exception:
    EdgeTraceLineTool = EdgeTraceCircleTool = EdgeTraceCurveTool = None

try:
    from core.tools.presence_absence import PresenceAbsenceTool
except Exception:
    PresenceAbsenceTool = None

try:
    from core.tools.yolo_roi import YoloROITool
except Exception:
    YoloROITool = None

try:
    from config.plc_map import CO_READY, CO_BUSY, CO_RESULT_OK, CO_RESULT_NOK
except Exception:
    CO_READY=CO_BUSY=CO_RESULT_OK=CO_RESULT_NOK=0


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
        self.tool_strip.enable_keyboard(self)

        # nový panel – jednoducho: ak sa zmení parameter, aplikuj na aktívny nástroj
        self.live_panel.paramsChanged.connect(lambda: self.live_panel.apply_to_tool(self._active_tool()))
        self.live_panel.loadClicked.connect( lambda: self.live_panel.fill_from_tool(self._active_tool()))
        self.live_panel.resetClicked.connect(lambda: self.live_panel.fill_from_tool(self._active_tool()))
        self.live_panel.saveClicked.connect( self._save_live_to_recipe)
        self.plc = None

        self.btn_cycle.clicked.connect(self._cycle_now)
        self.btn_trigger.clicked.connect(self._trigger_now)
        self.btn_save_ok.clicked.connect(self._save_ok)
        self.btn_save_nok.clicked.connect(self._save_nok)



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

        # --- ŽIVÉ LADENIE (nový widget) ---
        self.live_panel = LiveTuningPanel()

        # Posledné merania (vytvoríme widget)
        self.lbl_last = QtWidgets.QTextEdit()
        self.lbl_last.setReadOnly(True)

        # Pravý panel – pridaj všetky prvky v poradí
        right.addWidget(self.lbl_verdict)
        right.addWidget(self.lbl_latency)
        right.addWidget(self.chk_plc)
        right.addWidget(self.lbl_plc)
        right.addWidget(self.btn_cycle)
        right.addWidget(self.btn_trigger)
        right.addWidget(self.btn_save_ok)
        right.addWidget(self.btn_save_nok)
        right.addWidget(self.live_panel)
        right.addWidget(QtWidgets.QLabel("Posledné merania: preproc"))
        right.addWidget(self.lbl_last)
        right.addStretch()

        top.addWidget(self.view, 2)
        top.addLayout(right, 1)

        self.film = FilmstripWidget()

        # --- TOOL STRIP (náhľady nástrojov) ---
        self.tool_strip = ToolStrip()
        layout.addWidget(self.tool_strip, 0)


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

 
    # ---------- Render ----------
    def _render_out(self, frame_gray, out):
        ok = out.get("ok", True)
        self.lbl_verdict.setText("OK" if ok else "NOK")
        self.lbl_verdict.setStyleSheet(
            "QLabel{font-size:28px; padding:8px; border-radius:8px; background:%s; color:white;}" %
            ("#2e7d32" if ok else "#c62828")
        )
        self.lbl_latency.setText(f"lat: {out.get('elapsed_ms',0.0):.1f} ms")
        
        
        # udrž strip synchronizovaný s počtom nástrojov a základným obrázkom
        tools = getattr(self.state.pipeline, "tools", []) or []
        ref_for_strip = getattr(self.state, "ref_img", None)
        if ref_for_strip is None:
            ref_for_strip = self._last_frame
        self.tool_strip.set_tools_if_needed(tools, ref_for_strip, self._last_frame)


        if self.state.ref_img is not None:
            ref_h, ref_w = self.state.ref_img.shape[:2]
        else:
            ref_h, ref_w = frame_gray.shape[:2]
        comp = compose_overlay(frame_gray, (ref_h, ref_w), out, self._visible_tool_idx)

        self.view.set_ndarray(comp)

        # zaktualizuj náhľady (OK/NOK pásik + tooltipy)
        self.tool_strip.update_status(out, getattr(self.state, "ref_img", None), self._last_frame)


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

            # >>> NOVÉ: vypíš reťazec predspracovania, ak ho tool poslal
            pre = details.get("preproc_desc")
            if pre:
                lines.append(f"   ↳ preproc: {pre}")

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
    
    



    def _on_tool_selected_from_strip(self, row: int):
        if row is None or row < 0:
            self._visible_tool_idx = None
        else:
            self._visible_tool_idx = int(row)

        # vždy prepnúť živé ladenie na vybraný tool
        self._sync_live_panel_for_tool(self._visible_tool_idx if self._visible_tool_idx is not None else -1)

        # re-render posledného výstupu (bez čakania na ďalší tick)
        if self._last_frame is not None and self._last_out is not None:
            self._render_out(self._last_frame, self._last_out)

        # fallback: ak nič nie je vybraté, vyber prvý
        if (self._visible_tool_idx is None) and (self.tool_strip.count() > 0):
            self.tool_strip.setCurrentRow(0)
            self._visible_tool_idx = 0
            # vždy prepni live panel na vybraný tool
            self._sync_live_panel_for_tool(self._visible_tool_idx if self._visible_tool_idx is not None else -1)




    


    
    def _active_tool_idx(self) -> int:
        row = self.tool_strip.currentRow()
        return row if row >= 0 else None

    def _active_tool(self):
        idx = self._active_tool_idx()
        tools = getattr(self.state.pipeline, "tools", []) or []
        if idx is None or idx >= len(tools): return None
        return tools[idx]

    def _tool_type(self, tool) -> str:
        """
        Zistí typ toolu bez spoliehania sa na `tool.type`.
        Vracia: "diff_from_ref" | "_wip_edge_line" | "_wip_edge_circle" | "_wip_edge_curve"
                | "presence_absence" | "yolo_roi" | ""
        """
        if tool is None:
            return ""

        # 1) Priamy atribút (ak by existoval)
        t = (getattr(tool, "type", None) or "")
        if isinstance(t, str) and t:
            return t.lower()

        # 2) Podľa triedy (isinstance)
        try:
            if DiffFromRefTool and isinstance(tool, DiffFromRefTool):
                return "diff_from_ref"
        except Exception:
            pass
        try:
            if EdgeTraceLineTool and isinstance(tool, EdgeTraceLineTool):
                return "_wip_edge_line"
            if EdgeTraceCircleTool and isinstance(tool, EdgeTraceCircleTool):
                return "_wip_edge_circle"
            if EdgeTraceCurveTool and isinstance(tool, EdgeTraceCurveTool):
                return "_wip_edge_curve"
        except Exception:
            pass
        try:
            if PresenceAbsenceTool and isinstance(tool, PresenceAbsenceTool):
                return "presence_absence"
        except Exception:
            pass
        try:
            if YoloROITool and isinstance(tool, YoloROITool):
                return "yolo_roi"
        except Exception:
            pass

        # 3) Fallback: podľa názvu modulu / triedy
        cls = tool.__class__
        mod = (getattr(cls, "__module__", "") or "").lower()
        name = (getattr(cls, "__name__", "") or "").lower()
        p = dict(getattr(tool, "params", {}) or {})

        if "diff_from_ref" in mod or "difffromref" in name:
            return "diff_from_ref"
        if "edge_trace" in mod or "edgetrace" in name:
            # rozhodni tvar podľa params.shape
            shape = (p.get("shape") or "").lower()
            if shape == "circle":
                return "_wip_edge_circle"
            if shape == "polyline":
                return "_wip_edge_curve"
            return "_wip_edge_line"
        if "presence" in mod:
            return "presence_absence"
        if "yolo" in mod:
            return "yolo_roi"

        # 4) Fallback: podľa sady parametrov
        keys = set(p.keys())
        if {"canny_lo","canny_hi","width"} & keys:
            return "_wip_edge_line"
        if {"minScore"} & keys:
            return "presence_absence"
        if {"conf_thres","iou_thres","max_det"} & keys:
            return "yolo_roi"

        return ""

    def _sync_live_panel_for_tool(self, row: int):
        tool = self._active_tool()
        typ = self._tool_type(tool)
        self.live_panel.show_for_type(typ)
        self.live_panel.fill_from_tool(tool)


    def _save_live_to_recipe(self):
        tool = self._active_tool()
        if not tool:
            QtWidgets.QMessageBox.information(self, "Zapísať do receptu", "Nie je vybraný žiadny nástroj.")
            return
        self.live_panel.apply_to_tool(tool)  # pre istotu

        try:
            if hasattr(self.state, "save_current_recipe"):
                self.state.save_current_recipe()
                QtWidgets.QMessageBox.information(self, "Zapísať do receptu", "Parametre nástroja boli uložené do receptu.")
            else:
                QtWidgets.QMessageBox.information(self, "Zapísať do receptu", "Parametre sú v pamäti nástroja. Ulož recept v História/Builder.")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Zapísať do receptu", f"Uloženie zlyhalo: {e}")


    

    # ---------- Cyklus ----------
    def _cycle_now(self):
        if self.state.pipeline is None or self.state.camera is None:
            return
        frm = self.state.get_frame(timeout_ms=150)
        if frm is None: return
        self._last_frame = frm.copy()
        self.live_panel.apply_to_tool(self._active_tool())


        out = self.state.process(frm)
        self._render_out(frm, out)
        self._last_out = out
        # nič ďalšie – _render_out už volá tool_strip.update_status(...)



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
                self.live_panel.apply_to_tool(self._active_tool())


                out = self.state.process(frm)
                self._last_out_from_plc = out
                return out
            self.plc.tick(do_cycle_capture)
            if self._last_out_from_plc is not None:
                self._render_out(frm, self._last_out_from_plc)
                self._last_out = self._last_out_from_plc
                # _render_out už robí tool_strip.update_status(...)



                try: self.plc.mb.set_coil(20, 0)
                except: pass
        else:
            self.live_panel.apply_to_tool(self._active_tool())
            out = self.state.process(frm)
            self._render_out(frm, out)
            self._last_out = out
            # _render_out už robí tool_strip.update_status(...)



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
