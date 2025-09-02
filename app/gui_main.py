# app/gui_main.py
import sys
from PyQt5 import QtWidgets, QtCore
from app.app_state import AppState
from app.tabs.teach_tab import TeachTab
from app.tabs.builder_tab import BuilderTab
from app.tabs.run_tab import RunTab
from app.tabs.history_tab import HistoryTab
from app.tabs.settings_tab import SettingsTab

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QC – Keyence-like MVP")
        self.resize(1280, 800)

        self.state = AppState()

        tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(tabs)

        self.teach = TeachTab(self.state, self)
        self.builder = BuilderTab(self.state, self)
        self.run = RunTab(self.state, self)
        self.history = HistoryTab(self.state, self)
        self.settings = SettingsTab(self.state, self)

        tabs.addTab(self.teach, "Teach")
        tabs.addTab(self.builder, "Builder")
        tabs.addTab(self.run, "RUN")
        tabs.addTab(self.history, "História")
        tabs.addTab(self.settings, "Nastavenia")

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
