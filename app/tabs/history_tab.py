# app/tabs/history_tab.py
from PyQt5 import QtWidgets, QtCore
import csv
from pathlib import Path

class HistoryTab(QtWidgets.QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._build()
        self.refresh()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ts","recipe","ok","elapsed_ms","measures_json","img_path"])
        self.table.horizontalHeader().setStretchLastSection(True)
        btn = QtWidgets.QPushButton("Obnoviť")
        layout.addWidget(self.table)
        layout.addWidget(btn)
        btn.clicked.connect(self.refresh)

    def refresh(self):
        p = Path("history/log.csv")
        if not p.exists():
            self.table.setRowCount(0); return
        rows = []
        with p.open("r", encoding="utf-8") as f:
            r = csv.reader(f)
            header = next(r, None)
            for row in r:
                rows.append(row)
        self.table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,val in enumerate(row):
                self.table.setItem(i,j, QtWidgets.QTableWidgetItem(val))
