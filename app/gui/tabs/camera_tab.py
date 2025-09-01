# app/gui/tabs/camera_tab.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QImage, QPixmap
import sys
import cv2
import numpy as np
from app.gui.ui_style import TOOLBUTTON  # a prípadne PRIMARY_BUTTON, ak používaš


# (voliteľné) jednoduché štýly
try:
    from app.gui.ui_style import TOOLBUTTON
except Exception:
    TOOLBUTTON = ""

def _cv2_to_qpixmap(gray_u8: np.ndarray) -> QPixmap:
    """Rýchly grayscale -> QPixmap konvertor (na minihistogram)."""
    if gray_u8.ndim != 2:
        raise ValueError("Expected grayscale image")
    h, w = gray_u8.shape
    qimg = QImage(gray_u8.data, w, h, w, QImage.Format_Grayscale8)
    return QPixmap.fromImage(qimg).scaledToWidth(240, Qt.SmoothTransformation)


class CameraTab(QWidget):
    """
    Nastavenia vstupu:
      • Zdroj: RTSP (IP kamera) alebo USB kamera
      • RTSP: IP, username, password (URL sa vyrába automaticky, ukladá sa do QSettings)
      • USB: index zariadenia, rozlíšenie, FPS, auto-exp / exp / gain
      • Transformácie: flip H/V, rotate90
      • Test & snapshot & malý histogram
      • Runtime štatistiky (FPS/rozlíšenie) – aktualizuje gui_main.py cez update_runtime_stats()
    """
    def __init__(self, logic):
        super().__init__()
        self.logic = logic
        self.qs = QSettings("QualityInspectionApp", "CameraSettings")

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        self.setLayout(root)

        # --- Výber zdroja ---
        src_row = QHBoxLayout()
        root.addLayout(src_row)
        src_row.addWidget(QLabel("Zdroj:"))
        self.source_combo = QComboBox()
        self.source_combo.addItem("RTSP (IP kamera)", userData="rtsp")
        self.source_combo.addItem("USB kamera", userData="usb")
        src_row.addWidget(self.source_combo, 1)

        # --- RTSP panel ---
        self.rtsp_panel = QWidget()
        f_rtsp = QFormLayout(self.rtsp_panel)
        f_rtsp.setContentsMargins(0, 0, 0, 0)

        # načítaj uložené hodnoty (fallback prázdny reťazec)
        ip_def  = self.qs.value("rtsp/ip", "", str)
        usr_def = self.qs.value("rtsp/username", "", str)
        pwd_def = self.qs.value("rtsp/password", "", str)

        self.ip_input = QLineEdit(ip_def)
        self.username_input = QLineEdit(usr_def)
        self.password_input = QLineEdit(pwd_def)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.rtsp_url_label = QLabel("(rtsp url sa generuje automaticky)")
        self.rtsp_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f_rtsp.addRow("IP adresa:", self.ip_input)
        f_rtsp.addRow("Username:", self.username_input)
        f_rtsp.addRow("Password:", self.password_input)
        f_rtsp.addRow("RTSP URL:", self.rtsp_url_label)

        # --- USB panel ---
        self.usb_panel = QWidget()
        f_usb = QFormLayout(self.usb_panel)
        f_usb.setContentsMargins(0, 0, 0, 0)

        # USB device index
        dev_row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.btn_refresh = QPushButton("Obnoviť")
        self.btn_test_usb = QPushButton("Test")
        self.btn_refresh.setStyleSheet(TOOLBUTTON)
        self.btn_test_usb.setStyleSheet(TOOLBUTTON)
        dev_row.addWidget(self.device_combo, 1)
        dev_row.addWidget(self.btn_refresh)
        dev_row.addWidget(self.btn_test_usb)
        f_usb.addRow("Zariadenie:", dev_row)

        # Rozlíšenie + FPS
        self.width_spin = QSpinBox();     self.width_spin.setRange(0, 10000);  self.width_spin.setValue(0)
        self.height_spin = QSpinBox();    self.height_spin.setRange(0, 10000); self.height_spin.setValue(0)
        self.fps_spin = QDoubleSpinBox(); self.fps_spin.setRange(0.0, 1000.0); self.fps_spin.setDecimals(2); self.fps_spin.setValue(0.0)
        wh_row = QHBoxLayout()
        wh_row.addWidget(QLabel("W:")); wh_row.addWidget(self.width_spin)
        wh_row.addSpacing(6)
        wh_row.addWidget(QLabel("H:")); wh_row.addWidget(self.height_spin)
        wh_row.addSpacing(6)
        wh_row.addWidget(QLabel("FPS:")); wh_row.addWidget(self.fps_spin)
        f_usb.addRow("Rozlíšenie/FPS:", wh_row)

        # Auto expo / expo / gain
        self.auto_exp = QCheckBox("Auto")
        self.exposure_spin = QDoubleSpinBox(); self.exposure_spin.setRange(-20_000.0, 20_000.0); self.exposure_spin.setDecimals(2); self.exposure_spin.setValue(0.0)
        self.gain_spin = QDoubleSpinBox();     self.gain_spin.setRange(0.0, 1023.0);            self.gain_spin.setDecimals(1);   self.gain_spin.setValue(0.0)
        eg_row = QHBoxLayout()
        eg_row.addWidget(self.auto_exp)
        eg_row.addSpacing(6)
        eg_row.addWidget(QLabel("Exposure:")); eg_row.addWidget(self.exposure_spin)
        eg_row.addSpacing(6)
        eg_row.addWidget(QLabel("Gain:"));     eg_row.addWidget(self.gain_spin)
        f_usb.addRow("Expozícia:", eg_row)

        # Snapshot + histogram
        self.btn_snapshot = QPushButton("Snapshot")
        self.btn_snapshot.setStyleSheet(TOOLBUTTON)
        self.hist_label = QLabel("—")
        self.hist_label.setAlignment(Qt.AlignCenter)
        self.hist_label.setFixedHeight(90)
        self.hist_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        f_usb.addRow(self.btn_snapshot, self.hist_label)

        # --- Transformácie (spoločné) ---
        tf_row = QHBoxLayout()
        self.flip_h = QCheckBox("Flip H")
        self.flip_v = QCheckBox("Flip V")
        self.rotate90 = QCheckBox("Rotate 90°")
        for w in (self.flip_h, self.flip_v, self.rotate90):
            tf_row.addWidget(w)
        root.addLayout(tf_row)

        # --- Runtime štatistiky ---
        self.stats_label = QLabel("FPS: —   |   Rozlíšenie: —")
        self.stats_label.setAlignment(Qt.AlignLeft)
        root.addWidget(self.stats_label)

        # --- Test RTSP ---
        self.btn_test_rtsp = QPushButton("Test RTSP")
        self.btn_test_rtsp.setStyleSheet(TOOLBUTTON)
        root.addWidget(self.btn_test_rtsp)

        # --- Panel prepínač ---
        root.addWidget(self.rtsp_panel)
        root.addWidget(self.usb_panel)
        self._switch_panels(self.source_combo.currentData())

        # --- Handlery ---
        self.source_combo.currentIndexChanged.connect(
            lambda _: self._switch_panels(self.source_combo.currentData())
        )

        # priebežné ukladanie do QSettings + update URL
        self.ip_input.textChanged.connect(self._on_rtsp_inputs_changed)
        self.username_input.textChanged.connect(self._on_rtsp_inputs_changed)
        self.password_input.textChanged.connect(self._on_rtsp_inputs_changed)
        self._update_rtsp_url()

        self.btn_refresh.clicked.connect(self._refresh_devices)
        self.btn_test_usb.clicked.connect(self._test_usb)
        self.btn_snapshot.clicked.connect(self._snapshot_hist)
        self.btn_test_rtsp.clicked.connect(self._test_rtsp)

        # init USB zoznam
        self._refresh_devices()

    # ---------------- verejné API ----------------
    def get_source_config(self) -> dict:
        """Zober aktuálne nastavenia zdroja pre gui_main."""
        common = {
            "flip_h": self.flip_h.isChecked(),
            "flip_v": self.flip_v.isChecked(),
            "rotate90": self.rotate90.isChecked(),
        }
        if self.source_combo.currentData() == "usb":
            return {
                "type": "usb",
                "index": int(self.device_combo.currentData() or 0),
                "width": int(self.width_spin.value()),
                "height": int(self.height_spin.value()),
                "fps": float(self.fps_spin.value()),
                "auto_exposure": self.auto_exp.isChecked(),
                "exposure": None if self.auto_exp.isChecked() else float(self.exposure_spin.value()),
                "gain": float(self.gain_spin.value()),
                **common
            }
        else:
            ip = self.ip_input.text().strip()
            user = self.username_input.text().strip()
            pwd = self.password_input.text().strip()
            url = f"rtsp://{user}:{pwd}@{ip}:554/stream1" if ip else ""
            return {
                "type": "rtsp",
                "ip": ip,
                "username": user,
                "password": pwd,
                "url": url,
                **common
            }

    def update_runtime_stats(self, fps: float | None, resolution: tuple[int, int] | None):
        """Volá gui_main.show_frame – zobrazenie FPS a prípadne rozlíšenia."""
        fps_txt = f"{fps:.1f}" if fps is not None else "—"
        res_txt = f"{resolution[0]}×{resolution[1]}" if resolution else "—"
        self.stats_label.setText(f"FPS: {fps_txt}   |   Rozlíšenie: {res_txt}")

    # ---------------- interné helpery ----------------
    def _switch_panels(self, key: str):
        self.rtsp_panel.setVisible(key == "rtsp")
        self.usb_panel.setVisible(key == "usb")

    def _on_rtsp_inputs_changed(self, _=None):
        # priebežné ukladanie do QSettings
        self.qs.setValue("rtsp/ip", self.ip_input.text().strip())
        self.qs.setValue("rtsp/username", self.username_input.text().strip())
        self.qs.setValue("rtsp/password", self.password_input.text().strip())
        self._update_rtsp_url()

    def _update_rtsp_url(self):
        ip = self.ip_input.text().strip()
        user = self.username_input.text().strip()
        pwd = self.password_input.text().strip()
        url = f"rtsp://{user}:{pwd}@{ip}:554/stream1" if ip else "(—)"
        self.rtsp_url_label.setText(url)

    def _win_backend(self):
        if sys.platform.startswith("win"):
            return cv2.CAP_MSMF  # preferuj MSMF (stabilnejší index)
        elif sys.platform.startswith("linux"):
            return cv2.CAP_V4L2
        return None

    def _refresh_devices(self):
        """Enumerácia USB zariadení s vhodným backendom (Win: MSMF, Linux: V4L2)."""
        self.device_combo.clear()
        backend = self._win_backend()
        found = False
        for i in range(0, 6):  # limit 0..5 = rýchlejšie a bez zbytočných hlášok
            try:
                cap = cv2.VideoCapture(i, backend) if backend is not None else cv2.VideoCapture(i)
                ok = cap.isOpened()
                if ok:
                    name = cap.getBackendName() if hasattr(cap, "getBackendName") else "CAP"
                    self.device_combo.addItem(f"{i} ({name})", i)
                    found = True
            except Exception:
                pass
            finally:
                try:
                    cap.release()
                except Exception:
                    pass
        if not found:
            self.device_combo.addItem("Žiadne zariadenie", 0)

    def _test_usb(self):
        """Skúsi načítať 1 frame z vybraného USB indexu."""
        cfg = self.get_source_config()
        if cfg["type"] != "usb":
            self._flash_message("USB test: vyber USB zdroj")
            return
        backend = self._win_backend()
        cap = cv2.VideoCapture(cfg["index"], backend) if backend is not None else cv2.VideoCapture(cfg["index"])
        ok = cap.isOpened()
        if ok:
            # rozlíšenie / fps (ak zadané)
            if cfg["width"] > 0 and cfg["height"] > 0:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["width"])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["height"])
            if cfg["fps"] > 0:
                cap.set(cv2.CAP_PROP_FPS, cfg["fps"])
            ok, _ = cap.read()
        try:
            cap.release()
        except Exception:
            pass
        self._flash_message("✅ USB OK" if ok else "❌ USB sa nepodarilo načítať")

    def _test_rtsp(self):
        """Skúsi sa pripojiť na RTSP URL a načítať 1 frame."""
        cfg = self.get_source_config()
        if cfg["type"] != "rtsp" or not cfg.get("url"):
            self._flash_message("RTSP test: skontroluj IP/meno/heslo")
            return
        cap = cv2.VideoCapture(cfg["url"])
        ok = cap.isOpened()
        if ok:
            ok, _ = cap.read()
        try:
            cap.release()
        except Exception:
            pass
        self._flash_message("✅ RTSP OK" if ok else "❌ RTSP sa nepodarilo načítať")

    def _snapshot_hist(self):
        """Urobí snapshot z aktívneho zdroja a vykreslí malý histogram (len pre rýchlu optickú kontrolu)."""
        cfg = self.get_source_config()
        frame = None
        if cfg["type"] == "usb":
            backend = self._win_backend()
            cap = cv2.VideoCapture(cfg["index"], backend) if backend is not None else cv2.VideoCapture(cfg["index"])
        else:
            cap = cv2.VideoCapture(cfg["url"])

        ok = cap.isOpened()
        if ok:
            ok, frame = cap.read()
        try:
            cap.release()
        except Exception:
            pass

        if not ok or frame is None:
            self.hist_label.setText("no frame")
            return

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten()
        hist = hist / (hist.max() + 1e-9)

        h, w = 80, 240
        img = (np.ones((h, w), dtype=np.uint8) * 20)
        bin_w = w // len(hist)
        for i, v in enumerate(hist):
            cv2.rectangle(img, (i * bin_w, h - 1), ((i + 1) * bin_w - 1, int(h - v * (h - 4))), 200, -1)

        self.hist_label.setPixmap(_cv2_to_qpixmap(img))

    def _flash_message(self, text: str):
        self.stats_label.setText(text)
