# tabs/evaluation_tab.py
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QSpinBox, QLabel, QHBoxLayout, QToolButton
)
from PySide6.QtCore import Qt

try:
    from ui_style import TOOLBUTTON
except Exception:
    TOOLBUTTON = ""

class EvaluationTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QFormLayout(self)
        self.setLayout(layout)

        # --- Thresholdy ---
        self.conf_threshold = QSpinBox()
        self.conf_threshold.setRange(0, 100)
        self.conf_threshold.setValue(70)

        self.iou_threshold = QSpinBox()
        self.iou_threshold.setRange(0, 100)
        self.iou_threshold.setValue(50)

        layout.addRow(QLabel("<b>Detekcia</b>"))
        layout.addRow("Confidence threshold (%):", self.conf_threshold)
        layout.addRow("IoU threshold (%):", self.iou_threshold)

        # --- Funkcie (tool-buttons) ---
        layout.addRow(QLabel("<b>Signály / Ukladanie</b>"))

        self.tbtn_sound = QToolButton(); self._sty(self.tbtn_sound, "Zvukový alarm pri NOK", checkable=True)
        self.tbtn_led   = QToolButton(); self._sty(self.tbtn_led,   "LED signalizácia pri NOK", checkable=True)
        self.tbtn_save  = QToolButton(); self._sty(self.tbtn_save,  "Automaticky uložiť NOK obrázky", checkable=True)

        layout.addRow(self.tbtn_sound)
        layout.addRow(self.tbtn_led)
        layout.addRow(self.tbtn_save)

        layout.addRow(QLabel("<b>Trigger</b>"))

        self.tbtn_trigger = QToolButton(); self._sty(self.tbtn_trigger, "Externý trigger aktivovaný", checkable=True)
        trigger_row = QHBoxLayout()
        self.trigger_delay = QSpinBox()
        self.trigger_delay.setRange(0, 5000)
        self.trigger_delay.setValue(100)
        trigger_row.addWidget(self.tbtn_trigger)
        trigger_row.addWidget(QLabel("Delay (ms):"))
        trigger_row.addWidget(self.trigger_delay)
        layout.addRow(trigger_row)

        self.min_obj_size = QSpinBox()
        self.min_obj_size.setRange(0, 5000)
        self.min_obj_size.setValue(20)
        layout.addRow("Min veľkosť objektu (px):", self.min_obj_size)

        # centrálne nastavenia
        self.evaluation_settings = {
            "conf_threshold": self.conf_threshold.value(),
            "iou_threshold": self.iou_threshold.value(),
            "sound": False,
            "led": False,
            "auto_save_nok": False,
            "trigger": False,
            "trigger_delay": self.trigger_delay.value(),
            "min_obj_size": self.min_obj_size.value(),
        }

        # signály
        self.conf_threshold.valueChanged.connect(lambda v: self.evaluation_settings.update({"conf_threshold": v}))
        self.iou_threshold.valueChanged.connect(lambda v: self.evaluation_settings.update({"iou_threshold": v}))
        self.min_obj_size.valueChanged.connect(lambda v: self.evaluation_settings.update({"min_obj_size": v}))
        self.trigger_delay.valueChanged.connect(lambda v: self.evaluation_settings.update({"trigger_delay": v}))
        self.tbtn_sound.toggled.connect(lambda on: self.evaluation_settings.update({"sound": on}))
        self.tbtn_led.toggled.connect(lambda on: self.evaluation_settings.update({"led": on}))
        self.tbtn_save.toggled.connect(lambda on: self.evaluation_settings.update({"auto_save_nok": on}))
        self.tbtn_trigger.toggled.connect(lambda on: self.evaluation_settings.update({"trigger": on}))

    def _sty(self, btn: QToolButton, text: str, checkable=False):
        btn.setText(text)
        btn.setStyleSheet(TOOLBUTTON)
        btn.setCheckable(checkable)
