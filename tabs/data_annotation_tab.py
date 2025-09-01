# tabs/data_annotation_tab.py
import os
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QToolButton, QButtonGroup, QSplitter, QSizePolicy
)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtCore import Qt
from annotation_widget import AnnotationWidget
from widgets.class_bar import ClassBar

# štýly (voliteľné)
try:
    from ui_style import TOOLBUTTON, PRIMARY_BUTTON
except Exception:
    TOOLBUTTON = ""
    PRIMARY_BUTTON = ""

from annotation.roi_manager import clear_roi
from annotation.mask_manager import clear_masks


class DataAnnotationTab(QWidget):
    """
    Zber dát & Anotácia – layout:
      • ľavý panel (živý náhľad + kompaktné ovládanie)
      • pravý panel (AnnotationWidget – fotka sa fitne raz po načítaní)
    """
    def __init__(self, logic, frame_provider, start_live_callback, capture_callback, parent=None):
        super().__init__(parent)
        self.logic = logic
        self.frame_provider = frame_provider
        self.start_live_callback = start_live_callback
        self.capture_callback = capture_callback

        self.main_running = False
        self.setFocusPolicy(Qt.StrongFocus)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        self.setLayout(root)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)

        # ============= ĽAVÝ PANEL (live + ovládanie) =============
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(6)

        # Live stream náhľad
        self.image_label = QLabel("Live Stream")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black; color: white;")
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.image_label.setFixedHeight(220)
        left_layout.addWidget(self.image_label)

        # Live/Capture/Save
        self.btn_live = QToolButton();    self.btn_live.setText("Start Live")
        self.btn_capture = QToolButton(); self.btn_capture.setText("Odfotiť a anotovať")
        self.btn_save = QToolButton();    self.btn_save.setText("Uložiť anotáciu")
        for b in (self.btn_live, self.btn_capture, self.btn_save):
            b.setStyleSheet(TOOLBUTTON)
            left_layout.addWidget(b)

        # Triedy (labels) – ClassBar
        self.class_bar = ClassBar(self)
        self.current_class_name = None
        self.class_bar.classChanged.connect(lambda name: setattr(self, "current_class_name", name))
        left_layout.addWidget(self.class_bar)

        # Tool-paleta
        left_layout.addWidget(QLabel("Nástroje:"))

        def make_tool(text, checked=False, tooltip=None):
            btn = QToolButton()
            btn.setText(text)
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setMinimumWidth(120)
            btn.setStyleSheet(TOOLBUTTON)
            if tooltip:
                btn.setToolTip(tooltip)
            btn.setChecked(checked)
            return btn

        self.btn_tool_rect    = make_tool("Rect (R)",    checked=True,  tooltip="Kresli obdĺžnik")
        self.btn_tool_ellipse = make_tool("Ellipse (E)",                 tooltip="Kresli elipsu")
        self.btn_tool_poly    = make_tool("Polygon (P)",                 tooltip="Kresli polygon")
        self.btn_tool_roi     = make_tool("ROI (I)",                     tooltip="Vybrať oblasť ROI")
        self.btn_tool_mask    = make_tool("Mask (M)",                    tooltip="Definovať masku")
        self.btn_tool_mask.setEnabled(True)

        self.tools_group = QButtonGroup(self)
        self.tools_group.setExclusive(True)
        for b in (self.btn_tool_rect, self.btn_tool_ellipse, self.btn_tool_poly, self.btn_tool_roi, self.btn_tool_mask):
            self.tools_group.addButton(b)
            left_layout.addWidget(b)

        self.btn_tool_rect.toggled.connect(lambda on: on and self.set_tool("rect"))
        self.btn_tool_ellipse.toggled.connect(lambda on: on and self.set_tool("ellipse"))
        self.btn_tool_poly.toggled.connect(lambda on: on and self.set_tool("polygon"))
        self.btn_tool_roi.toggled.connect(lambda on: on and self.set_tool("roi"))
        self.btn_tool_mask.toggled.connect(lambda on: on and self.set_tool("mask"))

        # Edit + Reset sekcia
        left_layout.addWidget(QLabel("Úpravy:"))
        self.btn_undo  = QToolButton(); self.btn_undo.setText("Undo");       self.btn_undo.setStyleSheet(TOOLBUTTON)
        self.btn_clear = QToolButton(); self.btn_clear.setText("Clear All"); self.btn_clear.setStyleSheet(TOOLBUTTON)
        left_layout.addWidget(self.btn_undo)
        left_layout.addWidget(self.btn_clear)

        # Reset/clear ROI & masks
        self.btn_reset_roi   = QToolButton(); self.btn_reset_roi.setText("Reset ROI");     self.btn_reset_roi.setStyleSheet(TOOLBUTTON)
        self.btn_clear_masks = QToolButton(); self.btn_clear_masks.setText("Clear Masks"); self.btn_clear_masks.setStyleSheet(TOOLBUTTON)
        left_layout.addWidget(self.btn_reset_roi)
        left_layout.addWidget(self.btn_clear_masks)

        left_layout.addStretch(1)
        splitter.addWidget(left_panel)

        # ============= PRAVÝ PANEL (anotátor) =============
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.annotation_widget = AnnotationWidget()
        self.annotation_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout.addWidget(self.annotation_widget)

        splitter.addWidget(right_panel)
        splitter.setSizes([340, 1000])

        # Signály
        self.btn_live.clicked.connect(self.toggle_live)
        self.btn_capture.clicked.connect(self.capture_and_annotate)
        self.btn_save.clicked.connect(self.save_annotation)
        self.btn_undo.clicked.connect(self.annotation_widget.undo)
        self.btn_clear.clicked.connect(self.annotation_widget.clear_all)
        self.btn_reset_roi.clicked.connect(self._reset_roi)
        self.btn_clear_masks.clicked.connect(self._clear_masks)

        # klávesové skratky
        self._setup_shortcuts()

    # Tools
    def set_tool(self, tool: str):
        self.annotation_widget.tool = tool

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("R"), self, activated=lambda: self.btn_tool_rect.setChecked(True))
        QShortcut(QKeySequence("E"), self, activated=lambda: self.btn_tool_ellipse.setChecked(True))
        QShortcut(QKeySequence("P"), self, activated=lambda: self.btn_tool_poly.setChecked(True))
        QShortcut(QKeySequence("I"), self, activated=lambda: self.btn_tool_roi.setChecked(True))
        QShortcut(QKeySequence("M"), self, activated=lambda: self.btn_tool_mask.setChecked(True))
        # prepnúť ClassBar na "defekt"/"ok" ak existujú
        QShortcut(QKeySequence("D"), self, activated=lambda: self._set_label_if_exists("defekt"))
        QShortcut(QKeySequence("O"), self, activated=lambda: self._set_label_if_exists("ok"))

    def _set_label_if_exists(self, name: str):
        # ClassBar nepoužíva combobox; klikni na správny chip, ak existuje
        for b in getattr(self.class_bar, "buttons", []):
            if b.text() == name:
                b.click()
                break

    # Live
    def toggle_live(self):
        if self.main_running:
            self.start_live_callback("main", stop=True)
            self.main_running = False
            self.btn_live.setText("Start Live")
        else:
            self.start_live_callback("main", stop=False)
            self.main_running = True
            self.btn_live.setText("Stop Live")

    # Capture + anotácia
    def capture_and_annotate(self):
        """Odfotí frame, uloží do dataset/images/train a načíta do anotátora (fit spraví widget)."""
        import cv2
        frame = self.frame_provider()
        if frame is None:
            return

        os.makedirs("dataset/images/train", exist_ok=True)
        os.makedirs("dataset/labels/train", exist_ok=True)

        ts = int(time.time())
        img_path = os.path.join("dataset", "images", "train", f"capture_{ts}.png")

        cv2.imwrite(img_path, frame)
        self.annotation_widget.load_image(img_path)
        self.annotation_widget.setFocus()

    def save_annotation(self):
        label = self.current_class_name or "defekt"
        self.annotation_widget.save_labels(label)

    # Reset/clear handlers
    def _reset_roi(self):
        clear_roi()
        self.annotation_widget.reload_overlays()

    def _clear_masks(self):
        clear_masks()
        self.annotation_widget.reload_overlays()
