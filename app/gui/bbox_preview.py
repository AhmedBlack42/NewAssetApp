from __future__ import annotations

import hashlib

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class BoundingBoxPreview(QWidget):
    """Image preview with box geometry kept in original source pixel coordinates."""

    box_changed = Signal(int, list)
    box_created = Signal(list)
    box_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 160)
        self.setMouseTracking(True)
        self._pixmap = QPixmap()
        self._boxes: list[dict] = []
        self._selected: int | None = None
        self._gesture: dict | None = None
        self._zoom = 1.0
        self._pan = QPointF()
        self._labels_visible = False
        self._boxes_visible = True
        self._selected_only = False

    def set_image(self, path: str, boxes: list[dict] | None = None):
        self._pixmap = QPixmap(path)
        self._boxes = [dict(box) for box in (boxes or [])]
        self._selected = None
        self._gesture = None
        self._zoom = 1.0
        self._pan = QPointF()
        self.update()

    def set_boxes(self, boxes: list[dict]):
        selected = self._selected
        self._boxes = [dict(box) for box in boxes]
        self._selected = selected if any(int(b.get("id", -1)) == selected for b in self._boxes) else None
        self.update()

    def start_manual_box(self):
        self._gesture = {"kind": "create", "start": None}

    def selected_box(self):
        return next((box for box in self._boxes if int(box.get("id", -1)) == self._selected), None)

    def select_box(self, detection_id: int | None):
        ident = None if detection_id is None else int(detection_id)
        if ident is not None and not any(int(box.get("id", -1)) == ident for box in self._boxes):
            return False
        self._selected = ident
        self.update()
        return True

    def set_labels_visible(self, visible: bool):
        self._labels_visible = bool(visible)
        self.update()

    def set_boxes_visible(self, visible: bool):
        self._boxes_visible = bool(visible)
        self.update()

    def set_selected_only(self, visible: bool):
        self._selected_only = bool(visible)
        self.update()

    def _image_rect(self) -> QRectF:
        if self._pixmap.isNull():
            return QRectF()
        area = self.contentsRect()
        size = self._pixmap.size()
        scale = min(area.width() / size.width(), area.height() / size.height()) * self._zoom
        w, h = size.width() * scale, size.height() * scale
        return QRectF(area.center().x() - w / 2 + self._pan.x(),
                      area.center().y() - h / 2 + self._pan.y(), w, h)

    def _zoom_at(self, point: QPointF, factor: float):
        old = self._image_rect()
        if old.isEmpty():
            return
        new_zoom = max(1.0, min(8.0, self._zoom * factor))
        if new_zoom == self._zoom:
            return
        anchor_x = (point.x() - old.x()) / old.width()
        anchor_y = (point.y() - old.y()) / old.height()
        new_width = old.width() * new_zoom / self._zoom
        new_height = old.height() * new_zoom / self._zoom
        new_left = point.x() - anchor_x * new_width
        new_top = point.y() - anchor_y * new_height
        base_center_x = old.center().x() - self._pan.x()
        base_center_y = old.center().y() - self._pan.y()
        self._zoom = new_zoom
        self._pan = QPointF(new_left - (base_center_x - new_width / 2),
                            new_top - (base_center_y - new_height / 2))
        self.update()

    def _source_point(self, point: QPointF) -> QPointF:
        rect = self._image_rect()
        if rect.isEmpty():
            return QPointF()
        x = (point.x() - rect.x()) * self._pixmap.width() / rect.width()
        y = (point.y() - rect.y()) * self._pixmap.height() / rect.height()
        return QPointF(max(0, min(self._pixmap.width(), x)), max(0, min(self._pixmap.height(), y)))

    def _display_rect(self, box: dict) -> QRectF:
        image = self._image_rect()
        sx, sy = image.width() / self._pixmap.width(), image.height() / self._pixmap.height()
        x1, y1, x2, y2 = box["bbox_xyxy"]
        return QRectF(image.x() + x1 * sx, image.y() + y1 * sy,
                      (x2 - x1) * sx, (y2 - y1) * sy)

    @staticmethod
    def _detection_color(detection_id: int) -> QColor:
        digest = hashlib.sha256(str(int(detection_id)).encode("ascii")).digest()
        hue = int.from_bytes(digest[:4], "big") % 360
        saturation = 205 + digest[4] % 46
        value = 225 + digest[5] % 31
        return QColor.fromHsv(hue, saturation, value)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#0c1016"))
        if self._pixmap.isNull():
            painter.setPen(QColor("#929baa"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Select an image")
            return
        target = self._image_rect()
        painter.setClipRect(self.contentsRect())
        painter.drawPixmap(target, self._pixmap, self._pixmap.rect())
        if not self._boxes_visible:
            painter.end()
            return
        occupied_labels: list[QRectF] = []
        draw_boxes = []
        visible_boxes = [box for box in self._boxes
                         if not self._selected_only or int(box.get("id", -1)) == self._selected]
        for box in visible_boxes:
            ident = int(box.get("id", -1))
            rect = self._display_rect(box)
            color = self._detection_color(ident)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if ident == self._selected:
                painter.setPen(QPen(QColor("#11151c"), 4))
                painter.drawRect(rect)
                color = QColor(color)
                hue, _saturation, _value, _alpha = color.getHsv()
                color.setHsv(hue, 255, 255, 255)
            else:
                color.setAlpha(175)
            painter.setPen(QPen(color, 3 if ident == self._selected else 1.5))
            painter.drawRect(rect)
            draw_boxes.append((box, ident, rect, color))
            if ident == self._selected:
                color.setAlpha(190)
                painter.setBrush(color)
                painter.drawEllipse(QRectF(rect.right() - 5, rect.bottom() - 5, 10, 10))
                painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._labels_visible:
            font_metrics = painter.fontMetrics()
            candidates = [0, 1, 2, 3]
            for box, ident, rect, color in sorted(
                    draw_boxes, key=lambda item: (item[1] == self._selected, item[1])):
                label = str(box.get("class_name") or "detection")
                if len(label) > 24:
                    label = label[:21] + "…"
                label_width = min(max(58, font_metrics.horizontalAdvance(label) + 10), 190)
                label_height = 19
                positions = [
                    QRectF(rect.left(), rect.top() - label_height - 2, label_width, label_height),
                    QRectF(rect.left(), rect.bottom() + 2, label_width, label_height),
                    QRectF(rect.right() - label_width, rect.top() - label_height - 2,
                           label_width, label_height),
                    QRectF(rect.right() - label_width, rect.bottom() + 2, label_width, label_height),
                ]
                choices = []
                for order in candidates:
                    candidate = positions[order]
                    candidate.moveLeft(min(max(target.left(), candidate.left()),
                                           max(target.left(), target.right() - candidate.width())))
                    candidate.moveTop(min(max(target.top(), candidate.top()),
                                          max(target.top(), target.bottom() - candidate.height())))
                    label_overlap = sum(
                        max(0.0, candidate.intersected(occupied).width()) *
                        max(0.0, candidate.intersected(occupied).height())
                        for occupied in occupied_labels
                    )
                    box_overlap = sum(
                        max(0.0, candidate.intersected(other_rect).width()) *
                        max(0.0, candidate.intersected(other_rect).height())
                        for other_box, other_id, other_rect, _ in draw_boxes if other_id != ident
                    )
                    choices.append((label_overlap * 1000 + box_overlap, order, candidate,
                                    label_overlap, box_overlap))
                _, _, label_rect, label_overlap, box_overlap = min(
                    choices, key=lambda value: (value[0], value[1])
                )
                label_area = max(1.0, label_rect.width() * label_rect.height())
                if ident != self._selected and (
                        label_overlap > 0 or box_overlap > label_area * 0.2):
                    continue
                occupied_labels.append(label_rect)
                background = QColor("#11151c")
                background.setAlpha(170)
                painter.fillRect(label_rect, background)
                painter.setPen(color)
                painter.drawText(QPointF(label_rect.left() + 5,
                                         label_rect.top() + font_metrics.ascent() + 2), label)
        painter.end()

    def mousePressEvent(self, event):
        point = event.position()
        if event.button() == Qt.MouseButton.MiddleButton:
            self._gesture = {"kind": "pan", "start_widget": point, "original_pan": QPointF(self._pan)}
            return
        if self._gesture and self._gesture.get("kind") == "create":
            self._gesture["start"] = self._source_point(point)
            return
        for box in reversed(self._boxes):
            rect = self._display_rect(box)
            if rect.adjusted(-5, -5, 5, 5).contains(point):
                ident = int(box.get("id", -1))
                self._selected = ident
                self.box_selected.emit(ident)
                self._gesture = {"kind": "resize" if QRectF(rect.right()-10, rect.bottom()-10, 20, 20).contains(point)
                                 else "move", "id": ident, "start": self._source_point(point),
                                 "original": list(box["bbox_xyxy"])}
                self.update()
                return
        self._selected = None
        self._gesture = None
        self.update()

    def mouseMoveEvent(self, event):
        if not self._gesture:
            return
        if self._gesture["kind"] == "pan":
            self._pan = self._gesture["original_pan"] + event.position() - self._gesture["start_widget"]
            self.update()
            return
        if self._gesture.get("start") is None:
            return
        current = self._source_point(event.position())
        start = self._gesture["start"]
        if self._gesture["kind"] == "create":
            return
        box = next((b for b in self._boxes if int(b.get("id", -1)) == self._gesture["id"]), None)
        if not box:
            return
        x1, y1, x2, y2 = self._gesture["original"]
        dx, dy = current.x() - start.x(), current.y() - start.y()
        if self._gesture["kind"] == "move":
            width, height = x2 - x1, y2 - y1
            x1, y1 = max(0, min(self._pixmap.width() - width, x1 + dx)), max(0, min(self._pixmap.height() - height, y1 + dy))
            x2, y2 = x1 + width, y1 + height
        else:
            x2, y2 = max(x1 + 1, min(self._pixmap.width(), x2 + dx)), max(y1 + 1, min(self._pixmap.height(), y2 + dy))
        box["bbox_xyxy"] = [x1, y1, x2, y2]
        self._gesture["moved"] = self._gesture.get("moved", False) or box["bbox_xyxy"] != self._gesture["original"]
        box["edited"] = True
        self.update()

    def mouseReleaseEvent(self, event):
        gesture, self._gesture = self._gesture, None
        if not gesture or gesture.get("kind") == "pan" or gesture.get("start") is None:
            return
        if gesture["kind"] == "create":
            start, end = gesture["start"], self._source_point(event.position())
            box = [min(start.x(), end.x()), min(start.y(), end.y()),
                   max(start.x(), end.x()), max(start.y(), end.y())]
            if box[2] > box[0] and box[3] > box[1]:
                self.box_created.emit(box)
            return
        box = next((b for b in self._boxes if int(b.get("id", -1)) == gesture["id"]), None)
        if box and gesture.get("moved") and box["bbox_xyxy"] != gesture["original"]:
            self.box_changed.emit(int(box["id"]), list(box["bbox_xyxy"]))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self._zoom_at(event.position(), 1.15 if delta > 0 else 1 / 1.15)
            event.accept()
            return
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._zoom = 1.0
        self._pan = QPointF()
        self.update()
        event.accept()
