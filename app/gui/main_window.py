# gui_main.py
import sys, cv2
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QTabWidget
from PySide6.QtCore import Qt
from app.gui.tabs.data_annotation_tab import DataAnnotationTab
from app.gui.tabs.camera_tab import CameraTab
from app.gui.tabs.training_tab import TrainingTab
from app.gui.tabs.evaluation_tab import EvaluationTab
from app.gui.tabs.live_monitoring_tab import LiveMonitoringTab
from app.logic import AppLogic
from app.vision.ip_camera import IPCamera
from app.features.annotation.part_tracker import PartTracker
from app.vision.usb_camera import USBCamera
import time


class QualityApp(QWidget):
    def __init__(self,):
        super().__init__()
        self.setWindowTitle("Quality Inspection App")
        self.resize(1600, 900)

        # --- Logika ---
        self.logic = AppLogic()
        self.ip_camera = IPCamera()
        self.usb_camera = USBCamera()
        self.active_source = None   # "rtsp" alebo "usb"
        self._last_ts = None
        self._ema_fps = None

        self.part_tracker = PartTracker(model_path="yolov8n.pt")

        self.main_streaming = False
        self.live_streaming = False
        self.active_tab = None

        # --- Layout a tabs ---
        main_layout = QVBoxLayout(self)
        self.setLayout(main_layout)
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # --- Inštancia tabov ---
        self.annotation_tab = DataAnnotationTab(
            logic=self.logic,
            frame_provider=self.get_current_frame,
            start_live_callback=self.toggle_live_main,
            capture_callback=self.capture_and_update
        )
        self.settings_tab = CameraTab(self.logic)
        self.training_tab = TrainingTab()
        self.evaluation_tab = EvaluationTab()
        self.live_tab = LiveMonitoringTab(
            start_live_callback=self.toggle_live_monitoring,
            reset_stats_callback=self.reset_stats
        )

        # --- Pridanie tabov ---
        self.tabs.addTab(self.annotation_tab, "Zber dát & Anotácie")
        self.tabs.addTab(self.settings_tab, "Nastavenia kamery")
        self.tabs.addTab(self.training_tab, "Trénovanie modelu")
        self.tabs.addTab(self.evaluation_tab, "Evaluation Settings")
        self.tabs.addTab(self.live_tab, "Live Monitoring")

        self.tabs.currentChanged.connect(self.on_tab_changed)

        # keď dobehne tréning, načítaj nový model do live
        self.training_tab.model_ready.connect(self._swap_live_model)

    # ---------------- Live / toggle ----------------
    def toggle_live_main(self, target="main", stop=False):
        if stop:
            self.stop_live()
            self.main_streaming = False
            self.annotation_tab.btn_live.setText("Start Live")
        else:
            self.active_tab = "main"
            self.start_live()
            self.main_streaming = True
            self.annotation_tab.btn_live.setText("Stop Live")

    def toggle_live_monitoring(self, target="live", stop=False):
        if stop:
            self.stop_live()
            self.live_streaming = False
            self.live_tab.btn_live_start.setText("Start Live")
        else:
            self.active_tab = "live"
            self.start_live()
            self.live_streaming = True
            self.live_tab.btn_live_start.setText("Stop Live")

    def start_live(self):
        cfg = self.settings_tab.get_source_config()

        if cfg["type"] == "rtsp":
            # spusti RTSP
            self.ip_camera.start_stream(cfg["url"], self.show_frame)
            self.active_source = "rtsp"
        else:
            # spusti USB
            usb_settings = {
                "width": cfg.get("width", 0),
                "height": cfg.get("height", 0),
                "fps": cfg.get("fps", 0.0),
                "auto_exposure": cfg.get("auto_exposure", True),
                "exposure": cfg.get("exposure", None),
                "gain": cfg.get("gain", None),
            }

            backend = None
            if sys.platform.startswith("win"):
                backend = cv2.CAP_MSMF
            elif sys.platform.startswith("linux"):
                backend = cv2.CAP_V4L2
            self.usb_camera.start_stream(cfg["index"], self.show_frame, settings=usb_settings, backend=backend)

            self.active_source = "usb"

    def stop_live(self):
        # zastav obidva zdroje (pre istotu)
        try: self.ip_camera.stop_stream()
        except Exception: pass
        try: self.usb_camera.stop_stream()
        except Exception: pass

        self.active_source = None

        # reset UI
        self.annotation_tab.image_label.setText("Live stream zastavený")
        self.annotation_tab.image_label.setStyleSheet("background-color: black; color: white;")
        self.live_tab.live_image_label.setText("Live stream zastavený")
        self.live_tab.live_image_label.setStyleSheet("background-color: black; color: white;")

    def on_tab_changed(self, index):
        tab_text = self.tabs.tabText(index)
        if tab_text not in ["Zber dát & Anotácie", "Live Monitoring"]:
            self.stop_live()


    def get_current_frame(self):
        # vyber aktívny zdroj
        frame = self.usb_camera.get_current_frame() if self.active_source == "usb" \
                else self.ip_camera.get_current_frame()
        if frame is None:
            return None

        # aplikuj transformácie z CameraTab (flip/rotate)
        import cv2
        cfg = self.settings_tab.get_source_config()
        if cfg.get("flip_h"): frame = cv2.flip(frame, 1)
        if cfg.get("flip_v"): frame = cv2.flip(frame, 0)
        if cfg.get("rotate90"): frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        return frame


    # ---------------- Show Frame ----------------
    def show_frame(self, frame):
        import cv2
        from PySide6.QtGui import QImage, QPixmap

        # transformácie (flip/rotate) – nech je náhľad konzistentný s capture/anotáciou
        cfg = self.settings_tab.get_source_config()
        if cfg.get("flip_h"): frame = cv2.flip(frame, 1)
        if cfg.get("flip_v"): frame = cv2.flip(frame, 0)
        if cfg.get("rotate90"): frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        # FPS (EMA) – pošli do CameraTab
        t = time.time()
        if self._last_ts is not None:
            fps = 1.0 / max(1e-6, (t - self._last_ts))
            self._ema_fps = fps if self._ema_fps is None else (0.9 * self._ema_fps + 0.1 * fps)
            try:
                self.settings_tab.update_runtime_stats(self._ema_fps, None)
            except Exception:
                pass
        self._last_ts = t

        # vykreslenie / predikcie podľa aktívneho tabu
        if self.active_tab == "live":
            detections = self.part_tracker.predict(frame)
            conf_threshold = self.evaluation_tab.evaluation_settings.get("conf_threshold", 50) / 100.0
            for det in detections:
                if det["conf"] < conf_threshold: 
                    continue
                x1, y1, x2, y2 = map(int, det["bbox"])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0,255,0), 2)
                cv2.putText(frame, f"{det['label']} {det['conf']:.2f}", (x1, y1-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)

        # spoločná konverzia do QImage a vykreslenie
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)

        if self.active_tab == "main":
            self.annotation_tab.image_label.setPixmap(
                QPixmap.fromImage(qimg).scaled(320, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        # Live preview (aktualizujeme vždy, aby si mal veľký náhľad v Live tabu)
        self.live_tab.live_image_label.setPixmap(
            QPixmap.fromImage(qimg).scaled(640, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _swap_live_model(self, best_model_path: str):
        """
        Autoload nového modelu po tréningu.
        """
        try:
            self.part_tracker = PartTracker(model_path=best_model_path)
            # voliteľne: krátky toast/log – nechajme to jednoduché
            print(f"[Live] Načítaný nový model: {best_model_path}")
        except Exception as e:
            print(f"[Live] Nepodarilo sa načítať model {best_model_path}: {e}")


    # ---------------- Capture ----------------
    def capture_and_update(self, kind):
        frame = self.get_current_frame()

        if frame is not None:
            path = self.part_tracker.save_frame(frame, kind)
            self.logic.recent_photos.insert(0, (path, kind))
            if len(self.logic.recent_photos) > 50:
                self.logic.recent_photos.pop()


            # --- Trigger pre live monitoring ---
            detections = self.part_tracker.predict(frame)
            label_final = "NOK"
            conf_threshold = self.evaluation_tab.evaluation_settings.get("conf_threshold", 50) / 100
            for det in detections:
                if det["conf"] >= conf_threshold:
                    label_final = "OK"
                    break

            self.live_tab.evaluate_triggered_frame(label_final)

    # ---------------- Live Monitoring štatistiky ----------------
    def update_live_monitoring(self, label):
        self.live_tab.last_parts.insert(0, label)
        if len(self.live_tab.last_parts) > 10:
            self.live_tab.last_parts.pop()
        self.live_tab.last_parts_label.setText("Posledné diely: " + ", ".join(self.live_tab.last_parts))

        if label == "OK":
            self.live_tab.stats_ok += 1
        else:
            self.live_tab.stats_nok += 1

        self.live_tab.ok_count_label.setText(f"OK: {self.live_tab.stats_ok}")
        self.live_tab.nok_count_label.setText(f"NOK: {self.live_tab.stats_nok}")

    def reset_stats(self):
        self.live_tab.stats_ok = 0
        self.live_tab.stats_nok = 0
        self.live_tab.last_parts = []
        self.live_tab.last_parts_label.setText("Posledné diely: ---")
        self.live_tab.ok_count_label.setText("OK: 0")
        self.live_tab.nok_count_label.setText("NOK: 0")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QualityApp()
    window.show()
    sys.exit(app.exec())
