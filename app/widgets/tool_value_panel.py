# app/widgets/tool_value_panel.py
from PyQt5 import QtWidgets, QtCore, QtGui

class ToolValuePanel(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal(float, float)  # lsl, usl

    def __init__(self, parent=None, units="px"):
        super().__init__(parent)
        self.units = units
        self._build()

    def _build(self):
        layout = QtWidgets.QGridLayout(self)

        self.lbl_measured = QtWidgets.QLabel("Měřeno:")
        self.val_measured = QtWidgets.QLabel("--")
        self.lbl_units = QtWidgets.QLabel(self.units)

        self.lbl_lsl = QtWidgets.QLabel("Spodní (LSL):")
        self.edit_lsl = QtWidgets.QLineEdit()
        self.lbl_usl = QtWidgets.QLabel("Horní (USL):")
        self.edit_usl = QtWidgets.QLineEdit()

        self.status = QtWidgets.QLabel("OK/NOK")
        self.status.setAlignment(QtCore.Qt.AlignCenter)
        self.status.setStyleSheet("QLabel{padding:6px; border-radius:6px; background:#2e7d32; color:white;}")

        layout.addWidget(self.lbl_measured, 0,0)
        layout.addWidget(self.val_measured, 0,1)
        layout.addWidget(self.lbl_units,    0,2)
        layout.addWidget(self.lbl_lsl,      1,0)
        layout.addWidget(self.edit_lsl,     1,1,1,2)
        layout.addWidget(self.lbl_usl,      2,0)
        layout.addWidget(self.edit_usl,     2,1,1,2)
        layout.addWidget(self.status,       3,0,1,3)

        self.edit_lsl.editingFinished.connect(self._emit_change)
        self.edit_usl.editingFinished.connect(self._emit_change)

    def set_units(self, units: str):
        self.units = units
        self.lbl_units.setText(units)

    def set_measured(self, v: float, ok: bool):
        self.val_measured.setText(f"{v:.3f}")
        if ok:
            self.status.setText("OK")
            self.status.setStyleSheet("QLabel{padding:6px; border-radius:6px; background:#2e7d32; color:white;}")
        else:
            self.status.setText("NOK")
            self.status.setStyleSheet("QLabel{padding:6px; border-radius:6px; background:#c62828; color:white;}")

    def set_limits(self, lsl, usl):
        self.edit_lsl.setText("" if lsl is None else str(lsl))
        self.edit_usl.setText("" if usl is None else str(usl))

    def _emit_change(self):
        def tofloat(txt):
            try: return float(txt)
            except: return None
        lsl = tofloat(self.edit_lsl.text())
        usl = tofloat(self.edit_usl.text())
        self.changed.emit(lsl if lsl is not None else float("nan"),
                          usl if usl is not None else float("nan"))
