# app/gui_main.py
import sys
from PyQt5 import QtWidgets, QtCore, QtGui

from app.app_state import AppState
from app.tabs.teach_tab import TeachTab
from app.tabs.builder_tab import BuilderTab
from app.tabs.run_tab import RunTab
from app.tabs.history_tab import HistoryTab
from app.tabs.settings_tab import SettingsTab
from storage.settings_store import SettingsStore

# --- jednoduché QSS pre Dark/Light ---
DARK_QSS = """
QWidget { background-color: #202124; color: #e8eaed; }
QPushButton { background: #303134; color: #e8eaed; border: 1px solid #3c4043; padding:6px; border-radius:6px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit { background:#171717; color:#e8eaed; border:1px solid #3c4043; border-radius:6px; padding:4px; }
QGroupBox { border:1px solid #3c4043; border-radius:8px; margin-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 6px; padding:0 3px 0 3px; }
QTabBar::tab:selected { background:#303134; }
QTabBar::tab { padding:6px; }
"""

LIGHT_QSS = """
QWidget { background-color: #fafafa; color: #111; }
QPushButton { background: #fff; color: #111; border: 1px solid #ccc; padding:6px; border-radius:6px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit { background:#fff; color:#111; border:1px solid #ccc; border-radius:6px; padding:4px; }
QGroupBox { border:1px solid #ddd; border-radius:8px; margin-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 6px; padding:0 3px 0 3px; }
QTabBar::tab:selected { background:#eaeaea; }
QTabBar::tab { padding:6px; }
"""

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QC – Keyence-like MVP")
        self.resize(1280, 800)

        self.state = AppState()
        self._settings = SettingsStore()

        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        self.teach = TeachTab(self.state, self)
        self.builder = BuilderTab(self.state, self)
        self.run = RunTab(self.state, self)
        self.history = HistoryTab(self.state, self)
        self.settings_tab = SettingsTab(self.state, self)

        self.tabs.addTab(self.teach, "Teach")
        self.tabs.addTab(self.builder, "Builder")
        self.tabs.addTab(self.run, "RUN")
        self.tabs.addTab(self.history, "História")
        self.tabs.addTab(self.settings_tab, "Nastavenia")

        # prepojenie: zmeny témy z Nastavení
        self.settings_tab.themeChanged.connect(self._apply_theme)

        # aplikuj tému zo settings pri štarte
        self._apply_theme(self._settings.get_ui_theme())

        # menu s prepínačom témy
        self._build_menu()


    # --- aplikovanie témy + uloženie preferencie ---
    def _apply_theme(self, theme: str):
        theme = (theme or "dark").lower()
        qss = DARK_QSS if theme == "dark" else LIGHT_QSS
        QtWidgets.QApplication.instance().setStyleSheet(qss)
        # zapíš preferenciu (aby prežila reštart)
        self._settings.set_ui_theme(theme)

                # prekliknúť stav akcií v menu (ak už existujú)
        if hasattr(self, "act_theme_dark") and hasattr(self, "act_theme_light"):
            self.act_theme_dark.setChecked(theme == "dark")
            self.act_theme_light.setChecked(theme == "light")

    
    def _build_menu(self):
        menu_view = self.menuBar().addMenu("&Zobrazenie")

        # skupina pre checkovateľné akcie (exkluzívne)
        grp = QtWidgets.QActionGroup(self)
        grp.setExclusive(True)

        self.act_theme_dark = QtWidgets.QAction("Téma: Dark", self, checkable=True)
        self.act_theme_light = QtWidgets.QAction("Téma: Light", self, checkable=True)

        # skratky
        self.act_theme_dark.setShortcut("Ctrl+Alt+D")
        self.act_theme_light.setShortcut("Ctrl+Alt+L")

        grp.addAction(self.act_theme_dark)
        grp.addAction(self.act_theme_light)

        menu_view.addAction(self.act_theme_dark)
        menu_view.addAction(self.act_theme_light)

        # aktuálny stav zaškrtnutia podľa settings
        cur = (self._settings.get_ui_theme() or "dark").lower()
        self.act_theme_dark.setChecked(cur == "dark")
        self.act_theme_light.setChecked(cur == "light")

        # handlery
        self.act_theme_dark.triggered.connect(lambda: self._apply_theme("dark"))
        self.act_theme_light.triggered.connect(lambda: self._apply_theme("light"))


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
