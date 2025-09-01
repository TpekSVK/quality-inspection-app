from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPolygonItem,
    QGraphicsItem, QStyleOptionGraphicsItem
)
from PySide6.QtGui import QPixmap, QMouseEvent, QPen, QPolygonF, QBrush, QPainter, QTransform, QKeyEvent
from PySide6.QtCore import Qt, QRectF, QPointF
import os
import random

from annotation.label_manager import ensure_yaml, get_names, name_to_id
from annotation.roi_manager import save_roi, load_roi
from annotation.mask_manager import add_mask, load_masks


class ResizableRectItem(QGraphicsRectItem):
    HANDLE_SIZE = 8

    def __init__(self, rect: QRectF):
        super().__init__(rect)
        self.setFlags(
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self._resizing = False
        self._handle = None

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            r = self.rect().normalized()
            hs = self.HANDLE_SIZE
            for x in (r.left(), r.center().x() - hs/2, r.right() - hs):
                for y in (r.top(), r.center().y() - hs/2, r.bottom() - hs):
                    painter.fillRect(QRectF(x, y, hs, hs), Qt.blue)

    def hoverMoveEvent(self, event):
        self._handle = self._detect_handle(event.pos())
        if self._handle:
            self.setCursor(Qt.SizeAllCursor if self._handle == "center" else Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        self._handle = self._detect_handle(event.pos())
        if self._handle and self._handle != "center":
            self._resizing = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            r = self.rect()
            p = event.pos()
            r.setBottomRight(p)
            self.setRect(r.normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizing = False
        self._handle = None
        super().mouseReleaseEvent(event)

    def _detect_handle(self, pos: QPointF):
        r = self.rect().normalized()
        hs = self.HANDLE_SIZE
        if QRectF(r.right()-hs, r.bottom()-hs, hs, hs).contains(pos):
            return "br"
        if QRectF(r.center().x()-hs/2, r.center().y()-hs/2, hs, hs).contains(pos):
            return "center"
        return None


class AnnotationWidget(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)

        # === DÔLEŽITÉ PRE ZOOM NA KURZOR ===
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)  # stabilné scrollovanie; bez centrovania

        # auto-fit režim: len po načítaní (a po "F")
        self._auto_fit_on_resize = False
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.image_item = None
        self.current_item = None
        self.items = []
        self.rects = []
        self.image_path = None
        self.tool = "rect"       # rect, ellipse, polygon, roi, mask
        self.polygon_points = []
        self.mask_points = []

        # prekrytia
        self.roi_item = None
        self.mask_items = []

        # kvalita + pan
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.NoDrag)
        self._panning = False
        self._space_held = False

    # ---------- pomocné ----------
    def _fit(self):
        if self.image_item:
            self.fitInView(self.image_item, Qt.KeepAspectRatio)

    def _clear_overlays(self):
        if self.roi_item:
            self.scene.removeItem(self.roi_item)
            self.roi_item = None
        for it in self.mask_items:
            self.scene.removeItem(it)
        self.mask_items.clear()

    def _draw_overlays(self):
        """Načíta ROI/masky a vykreslí ich ako prekrytia, bez zachytávania myši."""
        # ROI
        roi = load_roi()
        if roi:
            x1, y1, x2, y2 = roi
            pen = QPen(Qt.green); pen.setWidth(2)
            self.roi_item = QGraphicsRectItem(QRectF(x1, y1, x2 - x1, y2 - y1))
            self.roi_item.setPen(pen)
            self.roi_item.setBrush(QBrush(Qt.transparent))
            self.roi_item.setZValue(10)
            self.roi_item.setAcceptedMouseButtons(Qt.NoButton)
            self.roi_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            self.roi_item.setFlag(QGraphicsItem.ItemIsFocusable, False)
            self.scene.addItem(self.roi_item)

        # Masks
        masks = load_masks()
        if masks:
            for pts in masks:
                poly = QPolygonF([QPointF(x, y) for x, y in pts])
                item = QGraphicsPolygonItem(poly)
                item.setPen(QPen(Qt.black, 1))
                item.setBrush(QBrush(Qt.black, Qt.SolidPattern))
                item.setOpacity(0.35)
                item.setZValue(9)
                item.setAcceptedMouseButtons(Qt.NoButton)
                item.setFlag(QGraphicsItem.ItemIsSelectable, False)
                item.setFlag(QGraphicsItem.ItemIsFocusable, False)
                self.scene.addItem(item)
                self.mask_items.append(item)

    def reload_overlays(self):
        self._clear_overlays()
        self._draw_overlays()

    # ---------- lifecycle ----------
    def load_image(self, path):
        self.scene.clear()
        self.items = []
        self.image_path = path
        self.polygon_points = []
        self.mask_points = []
        self.current_item = None
        self.roi_item = None
        self.mask_items = []

        pixmap = QPixmap(path)
        self.image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.image_item)
        self.setSceneRect(QRectF(pixmap.rect()))

        # prekrytia a fit
        self._auto_fit_on_resize = True     # jednorazový fit pri najbližšom resizovaní
        self._draw_overlays()
        self._fit()                         # a fit hneď teraz

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_fit_on_resize:
            self._fit()

    # ---------- interakcie ----------
    def fit_to_view(self):
        if self.image_item:
            self.setTransform(QTransform())           # reset zoom
            self.fitInView(self.image_item, Qt.KeepAspectRatio)
            self._auto_fit_on_resize = True           # po "F" znova auto-fit pri resize

    def wheelEvent(self, event):
        if not self.image_item:
            return super().wheelEvent(event)

        # po ručnom zoome už nerefituješ pri resize
        self._auto_fit_on_resize = False

        # bod pod kurzorom v scéne PRED zmenou mierky
        try:
            cursor_pos = event.position().toPoint()   # Qt6
        except AttributeError:
            cursor_pos = event.pos()
        old_scene_pos = self.mapToScene(cursor_pos)

        # smer a faktor zoomu
        delta = event.angleDelta().y() or event.angleDelta().x()
        factor = 1.15 if delta > 0 else (1/1.15)

        # limity zoomu (voliteľné)
        cur_scale = self.transform().m11()
        min_scale, max_scale = 0.1, 10.0
        new_scale = cur_scale * factor
        if new_scale < min_scale:
            factor = min_scale / cur_scale
        elif new_scale > max_scale:
            factor = max_scale / cur_scale

        # zmeň mierku
        self.scale(factor, factor)

        # nový bod pod kurzorom v scéne PO zmene mierky
        new_scene_pos = self.mapToScene(cursor_pos)

        # posuň tak, aby pôvodný bod ostal pod kurzorom
        delta_scene = new_scene_pos - old_scene_pos
        self.translate(delta_scene.x(), delta_scene.y())


    def mousePressEvent(self, event: QMouseEvent):
        # --- PAN START (middle, alebo Left + Space) ---
        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and self._space_held):
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        # --- /PAN START ---

        if not self.image_item:
            return

        pos = self.mapToScene(event.pos())
        pen = QPen(Qt.red); pen.setWidth(2)

        if self.tool == "rect":
            self.current_item = ResizableRectItem(QRectF(pos, pos))
            self.current_item.setPen(pen)
            self.scene.addItem(self.current_item)

        elif self.tool == "ellipse":
            self.current_item = QGraphicsEllipseItem(QRectF(pos, pos))
            self.current_item.setPen(pen)
            self.scene.addItem(self.current_item)

        elif self.tool == "polygon":
            self.polygon_points.append(pos)
            if len(self.polygon_points) > 1:
                if self.current_item:
                    self.scene.removeItem(self.current_item)
                polygon = QPolygonF(self.polygon_points)
                self.current_item = QGraphicsPolygonItem(polygon)
                self.current_item.setPen(pen)
                self.scene.addItem(self.current_item)

        elif self.tool == "roi":
            pen_roi = QPen(Qt.yellow); pen_roi.setWidth(2)
            self.current_item = QGraphicsRectItem(QRectF(pos, pos))
            self.current_item.setPen(pen_roi)
            self.scene.addItem(self.current_item)

        elif self.tool == "mask":
            self.mask_points.append(pos)
            if len(self.mask_points) > 1:
                if self.current_item:
                    self.scene.removeItem(self.current_item)
                poly = QPolygonF(self.mask_points)
                self.current_item = QGraphicsPolygonItem(poly)
                self.current_item.setPen(QPen(Qt.yellow, 2))
                self.current_item.setBrush(QBrush(Qt.transparent))
                self.scene.addItem(self.current_item)

    def mouseMoveEvent(self, event: QMouseEvent):
        # --- PAN MOVE ---
        if getattr(self, "_panning", False):
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        # --- /PAN MOVE ---

        if isinstance(self.current_item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            rect = QRectF(self.current_item.rect().topLeft(), self.mapToScene(event.pos()))
            self.current_item.setRect(rect.normalized())

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        # dokončenie masky (polygon) dvojklikom
        if self.tool == "mask" and len(self.mask_points) >= 3:
            pts = [(int(p.x()), int(p.y())) for p in self.mask_points]
            add_mask(pts)
            if self.current_item:
                self.scene.removeItem(self.current_item)
                self.current_item = None
            self.reload_overlays()
            self.mask_points = []
            print("✅ Maska pridaná.")
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        # --- PAN END ---
        if getattr(self, "_panning", False):
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        # --- /PAN END ---

        # ROI: ulož a prekresli overlay
        if isinstance(self.current_item, QGraphicsRectItem) and self.tool == "roi":
            rect = self.current_item.rect().toRect()
            x1, y1 = rect.x(), rect.y()
            x2, y2 = rect.x() + rect.width(), rect.y() + rect.height()
            save_roi(x1, y1, x2, y2)
            self.scene.removeItem(self.current_item)
            self.current_item = None
            self.reload_overlays()
            print(f"✅ ROI nastavené: {(x1, y1, x2, y2)}")
            return

        # Bežné tvary: rect/ellipse
        if isinstance(self.current_item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            r = self.current_item.rect().normalized()
            if r.width() < 2 or r.height() < 2:
                self.scene.removeItem(self.current_item)
            else:
                self.items.append(self.current_item)
                if isinstance(self.current_item, QGraphicsRectItem):
                    self.rects.append(self.current_item)
            self.current_item = None
            return

        # Polygon anotácia – zatiaľ bez akcie
        if self.tool == "polygon":
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        # Space = držaný pan modifier (pozri aj keyReleaseEvent)
        if event.key() == Qt.Key_Space:
            self._space_held = True
            if not self._panning:
                self.setCursor(Qt.OpenHandCursor)
            return

        if event.key() == Qt.Key_F:
            self.fit_to_view()
            return

        if event.key() == Qt.Key_Delete:
            for it in list(self.scene.selectedItems()):
                if it in self.items:
                    self.items.remove(it)
                self.scene.removeItem(it)
            return

        # jemný posun vybraných itemov (Shift = 10 px)
        delta = 10 if (event.modifiers() & Qt.ShiftModifier) else 1
        dx = dy = 0
        if event.key() == Qt.Key_Left:  dx = -delta
        if event.key() == Qt.Key_Right: dx =  delta
        if event.key() == Qt.Key_Up:    dy = -delta
        if event.key() == Qt.Key_Down:  dy =  delta
        if dx or dy:
            for it in self.scene.selectedItems():
                it.moveBy(dx, dy)
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Space:
            self._space_held = False
            if not self._panning:
                self.setCursor(Qt.ArrowCursor)
            return
        super().keyReleaseEvent(event)

    def undo(self):
        if self.items:
            last_item = self.items.pop()
            self.scene.removeItem(last_item)

    def clear_all(self):
        for item in self.items:
            self.scene.removeItem(item)
        self.items = []
        self.polygon_points = []

    # ---------- ukladanie YOLO labelov ----------
    def save_labels(self, label: str):
        """Uloží anotácie (rect/ellipse) do YOLO formátu a aktualizuje dataset.yaml."""
        if not self.image_path or not self.image_item:
            return

        os.makedirs("dataset/images/train", exist_ok=True)
        os.makedirs("dataset/images/val", exist_ok=True)
        os.makedirs("dataset/labels/train", exist_ok=True)
        os.makedirs("dataset/labels/val", exist_ok=True)

        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        subset = "train" if random.random() < 0.8 else "val"

        img_dest = os.path.join(f"dataset/images/{subset}", base_name + ".png")
        label_dest = os.path.join(f"dataset/labels/{subset}", base_name + ".txt")

        if self.image_path != img_dest:
            try:
                os.replace(self.image_path, img_dest)
            except Exception as e:
                print(f"⚠️ Nepodarilo sa presunúť obrázok: {e}")

        h = self.image_item.pixmap().height()
        w = self.image_item.pixmap().width()

        with open(label_dest, "w") as f:
            for item in self.items:
                if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
                    rect = item.rect().normalized()
                    x = rect.x(); y = rect.y()
                    rw = rect.width(); rh = rect.height()

                    x_center = (x + rw / 2) / w
                    y_center = (y + rh / 2) / h
                    rw /= w; rh /= h

                    cls_id = name_to_id(label)
                    f.write(f"{cls_id} {x_center:.6f} {y_center:.6f} {rw:.6f} {rh:.6f}\n")

        print(f"✅ Uložené: {img_dest}, {label_dest}")
        ensure_yaml(get_names())
