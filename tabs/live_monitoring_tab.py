# tabs/live_monitoring_tab.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton
from PySide6.QtCore import Qt

try:
    from ui_style import TOOLBUTTON, PRIMARY_BUTTON
except Exception:
    TOOLBUTTON = PRIMARY_BUTTON = ""

class LiveMonitoringTab(QWidget):
    def __init__(self, start_live_callback=None, reset_stats_callback=None):
        super().__init__()

        self.start_live_callback = start_live_callback
        self.reset_stats_callback = reset_stats_callback
        self.live_running = False

        # Štatistiky sa aktualizujú len pri triggeri
        self.stats_ok = 0
        self.stats_nok = 0
        self.last_parts = []

        layout = QVBoxLayout(self)

        # --- Live obraz ---
        self.live_image_label = QLabel("Live stream")
        self.live_image_label.setAlignment(Qt.AlignCenter)
        self.live_image_label.setStyleSheet("background-color: black; color: white;")
        self.live_image_label.setFixedSize(640, 480)
        layout.addWidget(self.live_image_label)

        # --- Štatistiky ---
        stats_group = QWidget()
        stats_layout = QVBoxLayout(stats_group)
        self.last_parts_label = QLabel("Posledné diely: ---")
        self.ok_count_label = QLabel("OK: 0")
        self.nok_count_label = QLabel("NOK: 0")
        stats_layout.addWidget(self.last_parts_label)
        stats_layout.addWidget(self.ok_count_label)
        stats_layout.addWidget(self.nok_count_label)
        layout.addWidget(stats_group)

        # --- Tlačidlá ---
        btn_layout = QHBoxLayout()
        self.btn_live_start = QToolButton()
        self.btn_live_start.setText("Start Live")
        self.btn_live_start.setCheckable(True)
        self.btn_live_start.setStyleSheet(PRIMARY_BUTTON)

        self.btn_reset_stats = QToolButton()
        self.btn_reset_stats.setText("Reset štatistiky")
        self.btn_reset_stats.setStyleSheet(TOOLBUTTON)

        btn_layout.addWidget(self.btn_live_start)
        btn_layout.addWidget(self.btn_reset_stats)
        layout.addLayout(btn_layout)

        self.btn_live_start.toggled.connect(self.toggle_live)
        self.btn_reset_stats.clicked.connect(self.reset_stats)

        # Prednastavený ROI alebo oblasť, ktorú model vyhodnocuje
        self.eval_region = None  # môže byť QRect alebo tuple(x1, y1, x2, y2)

    def toggle_live(self, checked: bool):
        if checked:
            if self.start_live_callback:
                self.start_live_callback("live", stop=False)
            self.live_running = True
            self.btn_live_start.setText("Stop Live")
        else:
            if self.start_live_callback:
                self.start_live_callback("live", stop=True)
            self.live_running = False
            self.btn_live_start.setText("Start Live")

    def reset_stats(self):
        self.stats_ok = 0
        self.stats_nok = 0
        self.last_parts = []
        self.last_parts_label.setText("Posledné diely: ---")
        self.ok_count_label.setText("OK: 0")
        self.nok_count_label.setText("NOK: 0")
        if self.reset_stats_callback:
            self.reset_stats_callback()

    def update_live_image(self, frame):
        """Zobrazenie live streamu bez aktualizácie počítadla"""
        import cv2
        from PySide6.QtGui import QImage, QPixmap

        # Ak je definovaná oblasť ROI, vyrežeme ju
        if self.eval_region:
            x1, y1, x2, y2 = self.eval_region
            frame = frame[y1:y2, x1:x2]

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        qt_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.live_image_label.setPixmap(QPixmap.fromImage(qt_image).scaled(
            640, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def evaluate_triggered_frame(self, label):
        """Aktualizuje štatistiky len pri triggeri (napr. odfotenie dielu)"""
        self.last_parts.insert(0, label)
        if len(self.last_parts) > 10:
            self.last_parts.pop()
        self.last_parts_label.setText("Posledné diely: " + ", ".join(self.last_parts))

        if label == "OK":
            self.stats_ok += 1
        else:
            self.stats_nok += 1

        self.ok_count_label.setText(f"OK: {self.stats_ok}")
        self.nok_count_label.setText(f"NOK: {self.stats_nok}")
