# app/gui/widgets/class_bar.py
from PySide6.QtWidgets import QWidget, QHBoxLayout, QToolButton, QMenu
from PySide6.QtGui import QAction
from PySide6.QtCore import Signal, Qt

try:
    from app.gui.ui_style import TOOLBUTTON, PRIMARY_BUTTON
except Exception:
    TOOLBUTTON = ""
    PRIMARY_BUTTON = ""

# PÔVODNE: from annotation.label_manager import ...
from app.features.annotation.label_manager import get_names, add_class, rename_class, remove_class
from app.gui.ui_style import TOOLBUTTON, PRIMARY_BUTTON

class ClassBar(QWidget):
    classChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(6)
        self.buttons = []
        self.active_name = None
        self._build()

    def _mk_btn(self, text: str, checked=False):
        b = QToolButton()
        b.setText(text)
        b.setCheckable(True)
        b.setChecked(checked)
        b.setStyleSheet(TOOLBUTTON)
        b.clicked.connect(lambda: self._on_select(text))
        # kontext menu (rename/delete)
        menu = QMenu(b)
        act_rename = QAction("Premenovať", b)
        act_delete = QAction("Odstrániť", b)
        menu.addAction(act_rename)
        menu.addAction(act_delete)
        act_rename.triggered.connect(lambda: self._rename(text))
        act_delete.triggered.connect(lambda: self._delete(text))
        b.setContextMenuPolicy(Qt.CustomContextMenu)
        b.customContextMenuRequested.connect(lambda pos, m=menu, w=b: m.exec(w.mapToGlobal(pos)))
        return b

    def _build(self):
        # clear
        while self.layout.count():
            w = self.layout.takeAt(0).widget()
            if w: w.deleteLater()
        self.buttons.clear()

        names = get_names()
        for i, n in enumerate(names):
            b = self._mk_btn(n, checked=(i==0 and self.active_name is None))
            self.layout.addWidget(b)
            self.buttons.append(b)

        # "+" button
        plus = QToolButton()
        plus.setText("+")
        plus.setStyleSheet(PRIMARY_BUTTON)
        plus.clicked.connect(self._add)
        self.layout.addWidget(plus)

        # set active
        if self.active_name is None and names:
            self.active_name = names[0]
            self.classChanged.emit(self.active_name)
        else:
            # re-check correct button
            for b in self.buttons:
                b.setChecked(b.text() == self.active_name)

        self.layout.addStretch(1)

    # events
    def _on_select(self, name: str):
        self.active_name = name
        for b in self.buttons:
            b.setChecked(b.text() == name)
        self.classChanged.emit(name)

    def _add(self):
        # jednoduché inline meno
        base = "class"
        names = get_names()
        i = 0
        new_name = f"{base}_{i}"
        while new_name in names:
            i += 1
            new_name = f"{base}_{i}"
        add_class(new_name)
        self.active_name = new_name
        self._build()

    def _rename(self, old_name: str):
        # jednoduché auto meno (ak chceš, sprav si QInputDialog)
        new_name = old_name + "_renamed"
        rename_class(old_name, new_name)
        if self.active_name == old_name:
            self.active_name = new_name
        self._build()

    def _delete(self, name: str):
        remove_class(name)
        if self.active_name == name:
            # aktivuj prvú dostupnú
            names = get_names()
            self.active_name = names[0] if names else None
        self._build()
