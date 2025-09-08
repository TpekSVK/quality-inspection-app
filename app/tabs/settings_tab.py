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
from app.widgets.recipe_picker import RecipePicker
from storage.recipe_store_json import RecipeStoreJSON


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
        self.recipe_picker = RecipePicker(self.state.current_recipe or "FORMA_X_PRODUCT_Y")
        f1.addRow("Aktívny recept:", self.recipe_picker)

        # NOVÉ: tlačidlo Odstrániť recept
        self.btn_recipe_del = QtWidgets.QPushButton("Odstrániť recept")
        self.btn_recipe_del.setToolTip("Zmaže celý recept (referencia, verzie, nastavenia nástrojov).")
        f1.addRow("", self.btn_recipe_del)

        # prepojenia
        self.recipe_picker.changed.connect(lambda name: setattr(self.state, "current_recipe", name))
        self.btn_recipe_del.clicked.connect(self._on_recipe_delete)

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

        # NOVÉ: typ kamery pre profil (rovnaké možnosti ako hlavný výber kamery)
        self.cmb_prof_type = QtWidgets.QComboBox()
        # skopíruj položky z hlavného comboboxu typov kamier
        for i in range(self.cmb_cam.count()):
            self.cmb_prof_type.addItem(self.cmb_cam.itemText(i))

        form_prof.addRow("Názov:", self.edit_prof_name)
        form_prof.addRow("Typ:", self.cmb_prof_type)      # ← NOVÉ
        form_prof.addRow("URL:", self.edit_prof_url)

        hb = QtWidgets.QHBoxLayout()
        self.btn_prof_add = QtWidgets.QPushButton("Uložiť profil")  # pôvodne "Pridať/Update"
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
            typ = p.get("type") or "RTSP (OpenCV/FFmpeg)"
            it = QtWidgets.QListWidgetItem(f"{p.get('name')}  |  {typ}  |  {p.get('url')}")
            it.setData(QtCore.Qt.UserRole, p)
            self.list_prof.addItem(it)

        # auto-vyplň aktívny profil
        act = self.settings.get_active()
        if act:
            self.edit_prof_name.setText(act.get("name",""))
            self.edit_prof_url.setText(act.get("url",""))
            typ = act.get("type") or "RTSP (OpenCV/FFmpeg)"
            idx = self.cmb_prof_type.findText(typ)
            if idx >= 0:
                self.cmb_prof_type.setCurrentIndex(idx)
            self.edit_rtsp.setText(act.get("url",""))


    def _on_prof_sel(self):
        it = self.list_prof.currentItem()
        if not it: return
        p = it.data(QtCore.Qt.UserRole)
        self.edit_prof_name.setText(p.get("name",""))
        self.edit_prof_url.setText(p.get("url",""))
        typ = p.get("type") or "RTSP (OpenCV/FFmpeg)"
        idx = self.cmb_prof_type.findText(typ)
        if idx >= 0:
            self.cmb_prof_type.setCurrentIndex(idx)

    def prof_add(self):
        name = self.edit_prof_name.text().strip()
        url  = self.edit_prof_url.text().strip()
        typ  = self.cmb_prof_type.currentText()
        if not name or not url:
            QtWidgets.QMessageBox.warning(self, "Profil", "Zadaj meno aj URL.")
            return
        self.settings.upsert_profile(name, url, typ)
        self._refresh_profiles()
        # aktualizuj aj hlavné polia kamery
        self.edit_rtsp.setText(url)
        idx = self.cmb_cam.findText(typ)
        if idx >= 0:
            self.cmb_cam.setCurrentIndex(idx)


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
        typ = p.get("type") or "RTSP (OpenCV/FFmpeg)"
        # nastav aj oba combá na typ
        idx_main = self.cmb_cam.findText(typ)
        if idx_main >= 0:
            self.cmb_cam.setCurrentIndex(idx_main)
        idx_prof = self.cmb_prof_type.findText(typ)
        if idx_prof >= 0:
            self.cmb_prof_type.setCurrentIndex(idx_prof)


    def apply(self):
        # 1) UI téma
        theme = self.cmb_theme.currentText().lower()
        self.settings.set_ui_theme(theme)
        self.themeChanged.emit(theme)

        # 2) recept
        name = self.recipe_picker.current()
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

    def _on_recipe_delete(self):
        name = (self.recipe_picker.current() or "").strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Recept", "Nie je vybraný žiadny recept.")
            return

        # potvrdenie
        ret = QtWidgets.QMessageBox.question(
            self, "Odstrániť recept",
            f"Naozaj odstrániť recept „{name}“?\n"
            f"Týmto zmažeš aj referenčnú fotku a uložené verzie.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No
        )
        if ret != QtWidgets.QMessageBox.Yes:
            return

        store = RecipeStoreJSON()
        ok = False
        try:
            ok = store.delete(name)
        except Exception as e:
            ok = False

        if ok:
            # ak bol aktuálny, zruš jeho výber
            if getattr(self.state, "current_recipe", "") == name:
                self.state.current_recipe = ""
            # refresh picker
            try:
                self.recipe_picker.set_current("")
                self.recipe_picker.refresh()
            except Exception:
                pass
            QtWidgets.QMessageBox.information(self, "Recept", f"Recept „{name}“ bol odstránený.")
        else:
            QtWidgets.QMessageBox.warning(self, "Recept", f"Recept „{name}“ sa nepodarilo odstrániť.")
