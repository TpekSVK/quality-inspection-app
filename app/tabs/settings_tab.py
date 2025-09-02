# app/tabs/settings_tab.py
import os
from PyQt5 import QtWidgets, QtCore
from interfaces.camera_dummy import DummyCamera
from io.cameras.rtsp_camera import RTSPCamera
from io.cameras.rtsp_gst_camera import RTSPGstCamera

class SettingsTab(QtWidgets.QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._build()

    def _build(self):
        layout = QtWidgets.QFormLayout(self)

        self.edit_recipe = QtWidgets.QLineEdit(self.state.current_recipe or "FORMA_X_PRODUCT_Y")

        self.cmb_cam = QtWidgets.QComboBox()
        self.cmb_cam.addItems(["DummyCamera","RTSP (OpenCV/FFmpeg)","RTSP (GStreamer HW)"])

        self.edit_rtsp = QtWidgets.QLineEdit(os.environ.get("RTSP_URL", "rtsp://user:pass@ip:554/stream2"))
        self.spin_latency = QtWidgets.QSpinBox(); self.spin_latency.setRange(0, 500); self.spin_latency.setValue(0)
        self.btn_apply = QtWidgets.QPushButton("Použiť nastavenia")

        layout.addRow("Aktívny recept:", self.edit_recipe)
        layout.addRow("Kamera:", self.cmb_cam)
        layout.addRow("RTSP URL:", self.edit_rtsp)
        layout.addRow("RTSP latency [ms] (GStreamer):", self.spin_latency)
        layout.addRow(self.btn_apply)

        self.btn_apply.clicked.connect(self.apply)

    def apply(self):
        # Recept
        name = self.edit_recipe.text().strip()
        try:
            self.state.build_from_recipe(name)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Chyba receptu", f"Recept sa nepodarilo načítať:\n{e}")
            return

        # Kamera
        cam_type = self.cmb_cam.currentText()
        try:
            if cam_type == "DummyCamera":
                cam = DummyCamera()
            elif cam_type == "RTSP (OpenCV/FFmpeg)":
                url = self.edit_rtsp.text().strip()
                cam = RTSPCamera(url)
            else:
                url = self.edit_rtsp.text().strip()
                cam = RTSPGstCamera(url, latency_ms=int(self.spin_latency.value()))
            self.state.set_camera(cam)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Chyba kamery", f"Kamera sa nepodarila spustiť:\n{e}")
            return

        QtWidgets.QMessageBox.information(self, "OK", f"Nahodený recept {name} a kamera {cam_type}.")
