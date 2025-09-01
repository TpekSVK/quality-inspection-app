# tabs/training_tab.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QSpinBox,
    QDoubleSpinBox, QProgressBar, QTextEdit, QToolButton, QButtonGroup
)
from PySide6.QtCore import Qt, QThread, Signal
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


class TrainingThread(QThread):
    progress_signal = Signal(str)
    finished_signal = Signal(str)
    best_model_signal = Signal(str)  # absolute path to best.pt

    def __init__(self, model_path, data_yaml, epochs, batch, lr):
        super().__init__()
        self.btn_check = QToolButton(); self.btn_check.setText("Skontrolovať dataset"); self.btn_check.setStyleSheet(TOOLBUTTON)
        self.btn_tune  = QToolButton(); self.btn_tune.setText("Kalibrovať prah (val)"); self.btn_tune.setStyleSheet(TOOLBUTTON)
        layout.addWidget(self.btn_check)
        layout.addWidget(self.btn_tune)

        self.btn_check.clicked.connect(self._do_check)
        self.btn_tune.clicked.connect(self._do_tune)

        self.model_path = model_path
        self.data_yaml = data_yaml
        self.epochs = epochs
        self.batch = batch
        self.lr = lr

def _do_check(self):
    try:
        rep = analyze_dataset("dataset")
        self.log_output.append("=== DATASET CHECK ===")
        self.log_output.append(rep)
        self.log_output.append("=====================")
    except Exception as e:
        self.log_output.append(f"❌ Dataset check zlyhal: {e}")

def _do_tune(self):
    """
    Jednoduchý kalibrátor: načíta posledný best model (assets/models/last_best.txt),
    spustí predikcie na val/ a odporučí prah (max F1). Ak sú dáta malé, funguje to rýchlo.
    """
    try:
        best_txt = os.path.join("assets","models","last_best.txt")
        if not os.path.exists(best_txt):
            self.log_output.append("ℹ️ Nenašiel som assets/models/last_best.txt. Najprv natrénuj model.")
            return
        best_path = open(best_txt,"r").read().strip()
        if not os.path.exists(best_path):
            self.log_output.append(f"ℹ️ Best model neexistuje: {best_path}")
            return
        # lazy import + výpočet
        from ultralytics import YOLO
        import glob, os
        import numpy as np

        model = YOLO(best_path)
        val_imgs = glob.glob(os.path.join("dataset","images","val","*.png")) + \
                   glob.glob(os.path.join("dataset","images","val","*.jpg")) + \
                   glob.glob(os.path.join("dataset","images","val","*.jpeg"))
        if not val_imgs:
            self.log_output.append("ℹ️ Žiadne obrázky v dataset/images/val/")
            return

        # zhromaždi všetky predikcie (conf) a GT prítomnosť (aspoň 1 box v labeli)
        y_true = []
        y_score = []
        for ip in val_imgs:
            base = os.path.splitext(os.path.basename(ip))[0]
            lp = os.path.join("dataset","labels","val", base + ".txt")
            has_obj = os.path.exists(lp) and (len([l for l in open(lp).read().strip().splitlines() if l.strip()])>0)
            preds = model.predict(ip, verbose=False, conf=0.001)[0]  # veľmi nízky conf, zoberieme max
            confs = preds.boxes.conf.cpu().numpy() if preds.boxes is not None and preds.boxes.conf is not None else np.array([])
            score = float(confs.max()) if confs.size else 0.0
            y_true.append(1 if has_obj else 0)
            y_score.append(score)

        # vyhodnoť prahy 0..1
        y_true = np.array(y_true, dtype=int)
        y_score = np.array(y_score, dtype=float)
        best_f1 = -1.0
        best_thr = 0.5
        for thr in np.linspace(0.05, 0.95, 19):
            y_pred = (y_score >= thr).astype(int)
            tp = int(((y_pred==1) & (y_true==1)).sum())
            fp = int(((y_pred==1) & (y_true==0)).sum())
            fn = int(((y_pred==0) & (y_true==1)).sum())
            prec = tp / (tp+fp) if (tp+fp)>0 else 0.0
            rec  = tp / (tp+fn) if (tp+fn)>0 else 0.0
            f1   = 2*prec*rec/(prec+rec) if (prec+rec)>0 else 0.0
            if f1 > best_f1:
                best_f1 = f1
                best_thr = thr

        self.log_output.append(f"🎯 Odporúčaný conf threshold ≈ {best_thr:.2f} (F1={best_f1:.3f})")
        self.log_output.append("➡️ Nastav ho v 'Evaluation Settings' ako Confidence threshold (%).")
    except Exception as e:
        self.log_output.append(f"❌ Kalibrátor prahu zlyhal: {e}")


    def run(self):
        self.progress_signal.emit(f"Načítavam model {self.model_path} ...")
        try:
            model = YOLO(self.model_path)
            results = model.train(
                data=self.data_yaml,
                epochs=self.epochs,
                batch=self.batch,
                lr0=self.lr,
                verbose=True
            )
            best_model = os.path.abspath(str(results.save_dir / "weights" / "best.pt"))
            os.makedirs(os.path.join("assets", "models"), exist_ok=True)
            with open(os.path.join("assets", "models", "last_best.txt"), "w") as fp:
                fp.write(best_model + "\n")

            self.best_model_signal.emit(best_model)
            self.finished_signal.emit(f"✅ Trénovanie dokončené! Najlepší model: {best_model}")
        except Exception as e:
            self.finished_signal.emit(f"❌ Chyba pri trénovaní: {e}")


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
        self.thread.progress_signal.connect(self.update_progress)
        self.thread.finished_signal.connect(self.training_finished)
        self.thread.best_model_signal.connect(self._on_best_model)
        self.thread.start()

    def update_progress(self, text):
        self.progress_label.setText(text)
        self.log_output.append(text)

    def training_finished(self, text):
        self.progress_label.setText(text)
        self.progress_bar.hide()
        self.log_output.append(text)

    def _on_best_model(self, path: str):
        self.model_ready.emit(path)
        self.log_output.append(f"🔁 Best model pripravený pre Live: {path}")
