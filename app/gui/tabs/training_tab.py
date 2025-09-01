# tabs/training_tab.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QSpinBox,
    QDoubleSpinBox, QProgressBar, QTextEdit, QToolButton, QButtonGroup
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from pathlib import Path
from PySide6.QtGui import QShortcut, QKeySequence
from tools.dataset_check import analyze_dataset
import os

try:
    from app.gui.ui_style import TOOLBUTTON, PRIMARY_BUTTON
except Exception:
    TOOLBUTTON = PRIMARY_BUTTON = ""

# Ultralytics YOLO
from ultralytics import YOLO

# Build dataset (voliteľne)
try:
    from tools.dataset_build import build_dataset
except Exception:
    build_dataset = None


from PySide6.QtCore import QThread, Signal
from pathlib import Path

class TrainingThread(QThread):
    """
    Worker thread pre YOLO tréning (bez UI prvkov).
    Signály:
      - log(str): textový priebežný log
      - progress_signal(int): priebeh 0..100
      - best_model_signal(str): cesta k best modelu (napr. .../weights/best.pt)
      - finished(object): {'save_dir': str|None} alebo {'error': str}
      - finished_signal(object): alias na finished (kompatibilita)
    """
    log = Signal(str)
    progress_signal = Signal(int)
    best_model_signal = Signal(str)
    finished = Signal(object)          # ✅ namiesto dict
    finished_signal = Signal(object)   # ✅ alias, tiež object

    def __init__(self, model_path: str, data_yaml: str, epochs: int, batch: int, lr: float, imgsz: int = 640):
        super().__init__()
        self._last_prog = -1
        self.model_path = model_path
        self.data_yaml = data_yaml
        self.epochs = int(epochs)
        self.batch = int(batch)
        self.lr = float(lr)
        self.imgsz = int(imgsz)
        self._best_emitted = set()

    def _emit_best_if_exists(self, save_dir: Path | None):
        if not save_dir:
            return
        for p in [save_dir / "weights" / "best.pt", save_dir / "weights" / "best.onnx",
                  save_dir / "best.pt", save_dir / "best.onnx"]:
            p = Path(p)
            if p.exists():
                s = str(p.resolve())
                if s not in self._best_emitted:
                    self._best_emitted.add(s)
                    self.best_model_signal.emit(s)

    def run(self):
        try:
            # vypnúť online checky (stabilita v PySide6+Shiboken)
            import os
            os.environ.setdefault("ULTRALYTICS_HUB", "0")
            os.environ.setdefault("ULTRALYTICS_UPDATE", "0")
            os.environ.setdefault("YOLO_VERBOSE", "0")

            from ultralytics import YOLO
            # umlčať sieťové kontroly (ak sú v tvojej verzii)
            try:
                import ultralytics.utils.checks as ychecks
                ychecks.is_online = lambda *a, **k: False
                ychecks.check_latest_pypi_version = lambda *a, **k: ""
                ychecks.check_pip_update_available = lambda *a, **k: False
            except Exception:
                pass

            self.progress_signal.emit(0)
            self.log.emit(
                f"Starting training: model={self.model_path}, data={self.data_yaml}, "
                f"epochs={self.epochs}, batch={self.batch}, lr0={self.lr}, imgsz={self.imgsz}"
            )

            model = YOLO(self.model_path)
            run_save_dir = None
            self._last_prog = -1  # debounce

            # --- definícia callbackov ---
            from pathlib import Path

            def _on_epoch_end(trainer):
                try:
                    total = int(getattr(trainer, "epochs", self.epochs) or self.epochs)
                    cur = int(getattr(trainer, "epoch", -1)) + 1
                    prog = int(max(0, min(100, round(cur / max(1, total) * 100))))
                    if prog != self._last_prog:
                        self.progress_signal.emit(prog)
                        self._last_prog = prog
                    if cur == 1 or cur % 5 == 0 or cur == total:
                        self.log.emit(f"Epoch {cur}/{total} done")

                    sd = Path(getattr(trainer, "save_dir", "")) if hasattr(trainer, "save_dir") else (run_save_dir or Path())
                    self._emit_best_if_exists(sd)

                    if self.isInterruptionRequested():
                        try:
                            trainer.stop_training = True
                        except Exception:
                            pass
                        self.log.emit("⏹️ Training stop requested; finishing current epoch…")
                except Exception as e:
                    try:
                        self.log.emit(f"[WARN] on_epoch_end: {e}")
                    except Exception:
                        pass

            def _on_model_save(trainer):
                try:
                    sd = Path(getattr(trainer, "save_dir", "")) if hasattr(trainer, "save_dir") else (run_save_dir or Path())
                    self._emit_best_if_exists(sd)
                except Exception:
                    pass

            # --- REGISTRÁCIA CALLBACKOV CEZ add_callback (nie cez callbacks=) ---
            try:
                model.add_callback("on_fit_epoch_end", _on_epoch_end)
            except Exception:
                pass
            try:
                model.add_callback("on_train_epoch_end", _on_epoch_end)  # pre iné verzie
            except Exception:
                pass
            try:
                model.add_callback("on_model_save", _on_model_save)
            except Exception:
                pass

            # --- TRÉNING BEZ 'callbacks=' ---
            results = model.train(
                data=self.data_yaml,
                epochs=self.epochs,
                batch=self.batch,
                lr0=self.lr,
                imgsz=self.imgsz,
                verbose=False,
            )

            self.progress_signal.emit(100)

            # finálne info o save_dir + pokus odoslať best.*
            try:
                from pathlib import Path as _P
                run_save_dir = _P(getattr(results, "save_dir", "")) if hasattr(results, "save_dir") else None
                self._emit_best_if_exists(run_save_dir)
            except Exception:
                pass

            payload = {"save_dir": str(run_save_dir) if run_save_dir else None}
            self.finished.emit(payload)
            self.finished_signal.emit(payload)

        except Exception as e:
            # log do súboru, aby si mal detail
            import traceback, datetime
            from pathlib import Path
            err_text = traceback.format_exc()
            log_dir = Path("logs"); log_dir.mkdir(exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            err_file = log_dir / f"training_error_{ts}.txt"
            try:
                err_file.write_text(err_text, encoding="utf-8")
            except Exception:
                pass
            self.log.emit(f"[ERR] {e}")
            payload = {"error": str(e), "error_file": str(err_file)}
            self.finished.emit(payload)
            self.finished_signal.emit(payload)

class TrainingTab(QWidget):
    model_ready = Signal(str)  # path to best.pt

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        self.setLayout(layout)
        layout.addWidget(QLabel("<b>Trénovanie YOLO modelu</b>"))

        # --- Parametre ---
        param_layout = QHBoxLayout()

        self.epochs_spin = QSpinBox(); self.epochs_spin.setRange(1, 500); self.epochs_spin.setValue(50)
        param_layout.addWidget(QLabel("Epochs:")); param_layout.addWidget(self.epochs_spin)

        self.batch_spin = QSpinBox(); self.batch_spin.setRange(1, 64); self.batch_spin.setValue(16)
        param_layout.addWidget(QLabel("Batch:")); param_layout.addWidget(self.batch_spin)

        self.lr_spin = QDoubleSpinBox(); self.lr_spin.setRange(0.00001, 1.0); self.lr_spin.setSingleStep(0.0001); self.lr_spin.setValue(0.01)
        param_layout.addWidget(QLabel("Learning rate:")); param_layout.addWidget(self.lr_spin)

        layout.addLayout(param_layout)

        # --- Výber modelu: paleta N/S/M/L ---
        layout.addWidget(QLabel("Model:"))
        models_row = QHBoxLayout()
        self.btn_n = self._mk_tool("yolov8n (N)", checked=True)
        self.btn_s = self._mk_tool("yolov8s (S)")
        self.btn_m = self._mk_tool("yolov8m (M)")
        self.btn_l = self._mk_tool("yolov8l (L)")
        for b in [self.btn_n, self.btn_s, self.btn_m, self.btn_l]:
            b.setStyleSheet(TOOLBUTTON); models_row.addWidget(b)
        layout.addLayout(models_row)

        self.models_group = QButtonGroup(self); self.models_group.setExclusive(True)
        for b in [self.btn_n, self.btn_s, self.btn_m, self.btn_l]:
            self.models_group.addButton(b)
        self.selected_model = "yolov8n.pt"
        self.btn_n.toggled.connect(lambda on: on and self._set_model("yolov8n.pt"))
        self.btn_s.toggled.connect(lambda on: on and self._set_model("yolov8s.pt"))
        self.btn_m.toggled.connect(lambda on: on and self._set_model("yolov8m.pt"))
        self.btn_l.toggled.connect(lambda on: on and self._set_model("yolov8l.pt"))

        QShortcut(QKeySequence("N"), self, activated=lambda: self.btn_n.setChecked(True))
        QShortcut(QKeySequence("S"), self, activated=lambda: self.btn_s.setChecked(True))
        QShortcut(QKeySequence("M"), self, activated=lambda: self.btn_m.setChecked(True))
        QShortcut(QKeySequence("L"), self, activated=lambda: self.btn_l.setChecked(True))

        # --- Build voľby ---
        layout.addWidget(QLabel("<b>Dataset build (voliteľné, bez zásahu do raw dát)</b>"))

        self.tbtn_build_masks = QToolButton()
        self.tbtn_build_masks.setText("Build s maskami (prekryť čiernou)")
        self.tbtn_build_masks.setCheckable(True); self.tbtn_build_masks.setChecked(False)
        self.tbtn_build_masks.setStyleSheet(TOOLBUTTON)
        layout.addWidget(self.tbtn_build_masks)

        self.tbtn_build_roi = QToolButton()
        self.tbtn_build_roi.setText("Build s ROI (orez & prepočet labelov)")
        self.tbtn_build_roi.setCheckable(True); self.tbtn_build_roi.setChecked(False)
        self.tbtn_build_roi.setEnabled(False)  # podľa tvojho rozhodnutia ROI nezapekať
        self.tbtn_build_roi.setStyleSheet(TOOLBUTTON)
        self.tbtn_build_roi.setToolTip("Vypnuté: ROI nechávame runtime (live). Zapni len ak cielene chceš orezaný build.")
        layout.addWidget(self.tbtn_build_roi)

        # --- Dataset YAML ---
        self.data_yaml_label = QLabel("Dataset YAML: dataset/dataset.yaml")
        layout.addWidget(self.data_yaml_label)

        # --- Štart tréningu ---
        self.train_btn = QToolButton(); self.train_btn.setText("Spustiť trénovanie"); self.train_btn.setStyleSheet(PRIMARY_BUTTON)
        layout.addWidget(self.train_btn)

        # --- Progress + logy ---
        self.progress_label = QLabel("Čaká sa na spustenie...")
        self.progress_bar = QProgressBar(); self.progress_bar.setRange(0, 0); self.progress_bar.hide()
        layout.addWidget(self.progress_label); layout.addWidget(self.progress_bar)

        self.log_output = QTextEdit(); self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)

        # signály
        self.train_btn.clicked.connect(self.start_training)

    def stop_training(self):
        if getattr(self, "thread", None):
            self._append_log("Stopping training…")
            # požiadaj vlákno o prerušenie
            self.thread.requestInterruption()

    def _cleanup_thread(self):
        t = getattr(self, "thread", None)
        if t is None:
            return
        try:
            t.wait(5000)  # počkaj max 5s nech sa pekne ukončí
        except Exception:
            pass
        try:
            t.deleteLater()
        except Exception:
            pass
        self.thread = None

    def _on_train_done(self, payload: dict | None = None):
        """Volá sa po skončení tréningu (úspech/ chyba)."""
        if payload and isinstance(payload, dict) and payload.get("error"):
            self._append_log(f"[ERR] {payload['error']}")
        else:
            save_dir = (payload or {}).get("save_dir")
            self._append_log(f"✅ Training finished" + (f" → {save_dir}" if save_dir else ""))

        # znovu povol tlačidlá (ak ich máš)
        for name in ("btn_start", "btn_stop", "btn_train"):
            if hasattr(self, name):
                try:
                    getattr(self, name).setEnabled(True)
                except Exception:
                    pass

        # uvoľni referenciu na thread
        if hasattr(self, "thread"):
            self.thread = None
    @Slot(str)
    def _append_log(self, text: str):
        """Bezpečné logovanie: do QTextEdit ak existuje, inak aspoň do konzoly."""
        try:
            # ak ešte nemáme log view, vytvoríme ho „lenive“
            if not hasattr(self, "log_view"):
                from PySide6.QtWidgets import QTextEdit, QVBoxLayout
                self.log_view = QTextEdit(self)
                self.log_view.setReadOnly(True)
                # pridaj do existujúceho root layoutu (alebo vytvor nový)
                lay = self.layout()
                if lay is None:
                    lay = QVBoxLayout(self)
                    self.setLayout(lay)
                lay.addWidget(self.log_view)
            # zapíš text
            self.log_view.append(text)
        except Exception:
            # fallback: aspoň nech to vidno v konzole
            print(text)

    def _mk_tool(self, text, checked=False):
        b = QToolButton(); b.setText(text); b.setCheckable(True); b.setChecked(checked); return b

    def _set_model(self, name):
        self.selected_model = name

    def start_training(self):
        base_yaml = "dataset/dataset.yaml"
        if not os.path.exists(base_yaml):
            self.progress_label.setText("❌ dataset.yaml neexistuje!")
            return

        data_yaml = base_yaml  # default: raw dataset
        if build_dataset and (self.tbtn_build_masks.isChecked() or self.tbtn_build_roi.isChecked()):
            try:
                self.progress_label.setText("Pripravujem build dataset...")
                self.progress_bar.show()
                self.log_output.append("🔧 Build dataset štart...")
                new_yaml = build_dataset(
                    apply_masks=self.tbtn_build_masks.isChecked(),
                    apply_roi=self.tbtn_build_roi.isChecked(),
                    src_root="dataset",
                    dst_root="dataset_build"
                )
                data_yaml = new_yaml
                self.log_output.append(f"📁 Build hotový: {new_yaml}")
                self.data_yaml_label.setText(f"Dataset YAML: {new_yaml}")
            except Exception as e:
                self.log_output.append(f"⚠️ Build zlyhal: {e}")
                # fallback na raw
                data_yaml = base_yaml

        self.progress_label.setText("Trénovanie prebieha...")
        self.progress_bar.show()
        self.log_output.append(f"Model: {self.selected_model}")
        self.log_output.append(f"Data:  {data_yaml}")

        model_path = self.selected_model
        epochs = self.epochs_spin.value()
        batch = self.batch_spin.value()
        lr = self.lr_spin.value()

        self.thread = TrainingThread(model_path, data_yaml, epochs, batch, lr)
        self.thread.log.connect(self._append_log)
        self.thread.progress_signal.connect(self.update_progress)
        self.thread.best_model_signal.connect(self._on_best_model)
        self.thread.finished.connect(self.training_finished)          # tvoj handler


        # 👇 dôležité: uprac vlákno po skončení
        self.thread.finished.connect(self._cleanup_thread)
        self.thread.finished_signal.connect(self._cleanup_thread)

        self.thread.start()

    @Slot(int)
    def update_progress(self, val: int):
        # progress bar (ak ho máš v UI)
        if hasattr(self, "progress_bar") and self.progress_bar:
            self.progress_bar.setValue(int(val))

        # textový label (urob si text tu, nie "text" prem.)
        if hasattr(self, "progress_label") and self.progress_label:
            self.progress_label.setText(f"{int(val)} %")



    @Slot(object)
    def training_finished(self, payload):
        """
        payload: dict ako {"save_dir": "..."} alebo {"error": "...", "error_file": "..."}.
        """
        is_err = False
        err_file = None

        # priprav správu pre UI/log
        if isinstance(payload, dict):
            if payload.get("error"):
                is_err = True
                err_file = payload.get("error_file")
                msg = f"❌ Training failed: {payload['error']}"
                if err_file:
                    msg += f"\nDetail log: {err_file}"
            else:
                sd = payload.get("save_dir") or "—"
                msg = f"✅ Training finished → {sd}"
        else:
            msg = str(payload)

        # progress do 100 % (tréning skončil – úspech alebo chyba)
        if hasattr(self, "progress_bar") and self.progress_bar:
            try:
                self.progress_bar.setValue(100)
            except Exception:
                pass

        # krátky text do labelu + celý text do tooltipu
        if hasattr(self, "progress_label") and self.progress_label:
            try:
                first_line = msg.splitlines()[0] if msg else ""
                self.progress_label.setText(first_line)
                self.progress_label.setToolTip(msg)  # celý detail nech je dostupný myšou
            except Exception:
                pass

        # výpis do log view a do konzoly (nech sa dá skopírovať)
        try:
            print(msg)
        except Exception:
            pass
        if hasattr(self, "_append_log"):
            try:
                self._append_log(msg)
            except Exception:
                pass

        # (voliteľné) zapamätaj si posledný error log pre rýchly prístup inde v UI
        if is_err and err_file:
            self.last_training_error_file = err_file

        # znovu povol tlačidlá (ak ich máš)
        for name in ("btn_start", "btn_stop", "btn_train"):
            if hasattr(self, name):
                try:
                    getattr(self, name).setEnabled(True)
                except Exception:
                    pass

        # uprac vlákno
        if hasattr(self, "_cleanup_thread"):
            self._cleanup_thread()

    @Slot(str)
    def _on_best_model(self, path: str):
        self._append_log(f"⭐ Best model saved: {path}")
        # ak máš textové pole pre model v UI:
        if hasattr(self, "txt_model_path"):
            try:
                self.txt_model_path.setText(path)
            except Exception:
                pass
        # krátky feedback do labelu
        if hasattr(self, "progress_label") and self.progress_label:
            self.progress_label.setText("Best model saved")