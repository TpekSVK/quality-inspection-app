# app/tabs/settings_tab.py
import os
from PyQt5 import QtWidgets, QtCore
from interfaces.camera_dummy import DummyCamera
from qcio.cameras.rtsp_camera import RTSPCamera
try:
    from qcio.cameras.rtsp_gst_camera import RTSPGstCamera
except Exception:
    RTSPGstCamera = None

from storage.settings_store import SettingsStore

class SettingsTab(QtWidgets.QWidget):
    # signal pre zmenu témy (dark/light)
    themeChanged = QtCore.pyqtSignal(str)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.settings = SettingsStore()
        self._build()
        self._refresh_profiles()
        self._load_ui_theme()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)

        # UI / Téma
        g0 = QtWidgets.QGroupBox("UI")
        f0 = QtWidgets.QFormLayout(g0)
        self.cmb_theme = QtWidgets.QComboBox()
        self.cmb_theme.addItems(["dark", "light"])
        f0.addRow("Téma:", self.cmb_theme)

        # Recept
        g1 = QtWidgets.QGroupBox("Recept")
        f1 = QtWidgets.QFormLayout(g1)
        self.edit_recipe = QtWidgets.QLineEdit(self.state.current_recipe or "FORMA_X_PRODUCT_Y")
        f1.addRow("Aktívny recept:", self.edit_recipe)

        # Kamera
        g2 = QtWidgets.QGroupBox("Kamera")
        f2 = QtWidgets.QFormLayout(g2)
        self.cmb_cam = QtWidgets.QComboBox()
        items = ["DummyCamera","RTSP (OpenCV/FFmpeg)"]
        if RTSPGstCamera is not None:
            items.append("RTSP (GStreamer HW)")
        self.cmb_cam.addItems(items)

        self.edit_rtsp = QtWidgets.QLineEdit(os.environ.get("RTSP_URL", "rtsp://user:pass@ip:554/stream2"))

        f2.addRow("Typ:", self.cmb_cam)
        f2.addRow("RTSP URL:", self.edit_rtsp)

        # Profily kamier
        g3 = QtWidgets.QGroupBox("Profily kamier")
        v3 = QtWidgets.QVBoxLayout(g3)
        self.list_prof = QtWidgets.QListWidget()
        form_prof = QtWidgets.QFormLayout()
        self.edit_prof_name = QtWidgets.QLineEdit()
        self.edit_prof_url = QtWidgets.QLineEdit()
        form_prof.addRow("Názov:", self.edit_prof_name)
        form_prof.addRow("URL:", self.edit_prof_url)
        hb = QtWidgets.QHBoxLayout()
        self.btn_prof_add = QtWidgets.QPushButton("Pridať/Update")
        self.btn_prof_del = QtWidgets.QPushButton("Odstrániť")
        self.btn_prof_use = QtWidgets.QPushButton("Použiť profil")
        hb.addWidget(self.btn_prof_add); hb.addWidget(self.btn_prof_del); hb.addWidget(self.btn_prof_use)
        v3.addWidget(self.list_prof)
        v3.addLayout(form_prof)
        v3.addLayout(hb)

        # Apply
        self.btn_apply = QtWidgets.QPushButton("Použiť nastavenia")

        layout.addWidget(g0)
        layout.addWidget(g1)
        layout.addWidget(g2)
        layout.addWidget(g3)
        layout.addWidget(self.btn_apply)

        # signály
        self.btn_apply.clicked.connect(self.apply)
        self.btn_prof_add.clicked.connect(self.prof_add)
        self.btn_prof_del.clicked.connect(self.prof_del)
        self.btn_prof_use.clicked.connect(self.prof_use)
        self.list_prof.itemSelectionChanged.connect(self._on_prof_sel)

    def _load_ui_theme(self):
        theme = self.settings.get_ui_theme()
        idx = self.cmb_theme.findText(theme or "dark")
        if idx >= 0:
            self.cmb_theme.setCurrentIndex(idx)

    def _refresh_profiles(self):
        self.list_prof.clear()
        for p in self.settings.profiles():
            it = QtWidgets.QListWidgetItem(f"{p.get('name')}  |  {p.get('url')}")
            it.setData(QtCore.Qt.UserRole, p)
            self.list_prof.addItem(it)
        # auto-vyplň aktívny profil
        act = self.settings.get_active()
        if act:
            self.edit_prof_name.setText(act.get("name",""))
            self.edit_prof_url.setText(act.get("url",""))
            self.edit_rtsp.setText(act.get("url",""))

    def _on_prof_sel(self):
        it = self.list_prof.currentItem()
        if not it: return
        p = it.data(QtCore.Qt.UserRole)
        self.edit_prof_name.setText(p.get("name",""))
        self.edit_prof_url.setText(p.get("url",""))

    def prof_add(self):
        name = self.edit_prof_name.text().strip()
        url  = self.edit_prof_url.text().strip()
        if not name or not url:
            QtWidgets.QMessageBox.warning(self, "Profil", "Zadaj meno aj URL.")
            return
        self.settings.upsert_profile(name, url)
        self._refresh_profiles()
        self.edit_rtsp.setText(url)

    def prof_del(self):
        it = self.list_prof.currentItem()
        if not it: return
        p = it.data(QtCore.Qt.UserRole)
        self.settings.delete_profile(p.get("name"))
        self._refresh_profiles()

    def prof_use(self):
        it = self.list_prof.currentItem()
        if not it: return
        p = it.data(QtCore.Qt.UserRole)
        self.settings.set_active(p.get("name"))
        self.edit_rtsp.setText(p.get("url",""))

    def apply(self):
        # 1) UI téma
        theme = self.cmb_theme.currentText().lower()
        self.settings.set_ui_theme(theme)
        self.themeChanged.emit(theme)

        # 2) recept
        name = self.edit_recipe.text().strip()
        try:
            self.state.build_from_recipe(name)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Chyba receptu", f"Recept sa nepodarilo načítať:\n{e}")
            return

        # 3) kamera
        cam_type = self.cmb_cam.currentText()
        try:
            if cam_type == "DummyCamera":
                cam = DummyCamera()
            elif cam_type == "RTSP (OpenCV/FFmpeg)":
                cam = RTSPCamera(self.edit_rtsp.text().strip())
            else:
                if RTSPGstCamera is None:
                    raise RuntimeError("GStreamer nie je k dispozícii")
                cam = RTSPGstCamera(self.edit_rtsp.text().strip(), latency_ms=0)
            self.state.set_camera(cam)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Chyba kamery", f"Kamera sa nepodarila spustiť:\n{e}")
            return

        QtWidgets.QMessageBox.information(self, "OK", f"Nahodený recept {name}, kamera {cam_type}, téma {theme}.")
