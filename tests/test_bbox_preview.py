import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint
from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.gui.bbox_preview import BoundingBoxPreview


class BoundingBoxPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.image = Path(self.temp.name) / "preview.png"
        Image.new("RGB", (100, 100), "white").save(self.image)
        self.widget = BoundingBoxPreview()
        self.widget.resize(200, 200)
        self.widget.set_image(str(self.image), [{"id": 7, "class_name": "face", "confidence": .8,
                                                   "bbox_xyxy": [20, 20, 60, 60], "origin": "ai"}])
        self.widget.show()
        self.app.processEvents()

    def tearDown(self):
        self.widget.close()
        self.temp.cleanup()

    def test_preview_selection_move_and_resize_use_source_coordinates(self):
        selected, changed = [], []
        self.widget.box_selected.connect(selected.append)
        self.widget.box_changed.connect(lambda ident, box: changed.append((ident, box)))
        rect = self.widget._display_rect(self.widget._boxes[0])
        center = QPoint(round(rect.center().x()), round(rect.center().y()))
        QTest.mouseClick(self.widget, QtMouse.Left, pos=center)
        self.assertEqual(selected, [7])
        image = self.widget._image_rect()
        start = QPoint(round(image.x() + image.width() * .4), round(image.y() + image.height() * .4))
        end = QPoint(round(image.x() + image.width() * .5), round(image.y() + image.height() * .5))
        QTest.mousePress(self.widget, QtMouse.Left, pos=start)
        QTest.mouseMove(self.widget, end, 30)
        QTest.mouseRelease(self.widget, QtMouse.Left, pos=end)
        self.assertEqual(changed[-1][0], 7)
        for actual, expected in zip(changed[-1][1], [30, 30, 70, 70]):
            self.assertAlmostEqual(actual, expected, delta=1.0)
        resized = self.widget._display_rect(self.widget._boxes[0])
        handle = QPoint(round(resized.right() - 2), round(resized.bottom() - 2))
        scale = self.widget._image_rect().width() / 100
        end = QPoint(round(handle.x() + 10 * scale), round(handle.y() + 10 * scale))
        before = list(self.widget._boxes[0]["bbox_xyxy"])
        QTest.mousePress(self.widget, QtMouse.Left, pos=handle)
        QTest.mouseMove(self.widget, end, 30)
        QTest.mouseRelease(self.widget, QtMouse.Left, pos=end)
        self.assertGreater(changed[-1][1][2], before[2])

    def test_selecting_a_box_without_drag_does_not_write_geometry(self):
        changed, selected = [], []
        self.widget.box_changed.connect(lambda ident, box: changed.append((ident, box)))
        self.widget.box_selected.connect(selected.append)
        rect = self.widget._display_rect(self.widget._boxes[0])
        QTest.mouseClick(self.widget, QtMouse.Left,
                         pos=QPoint(round(rect.center().x()), round(rect.center().y())))
        self.assertEqual(selected, [7])
        self.assertEqual(changed, [])

    def test_zoom_keeps_source_point_under_cursor(self):
        anchor = QPointF(120, 80)
        before = self.widget._source_point(anchor)
        self.widget._zoom_at(anchor, 1.5)
        after = self.widget._source_point(anchor)
        self.assertAlmostEqual(after.x(), before.x(), delta=1e-6)
        self.assertAlmostEqual(after.y(), before.y(), delta=1e-6)

    def test_preview_can_create_a_manual_source_coordinate_box(self):
        created = []
        self.widget.box_created.connect(created.append)
        self.widget.start_manual_box()
        image = self.widget._image_rect()
        start = QPoint(round(image.x() + image.width() * .2), round(image.y() + image.height() * .2))
        end = QPoint(round(image.x() + image.width() * .5), round(image.y() + image.height() * .5))
        QTest.mousePress(self.widget, QtMouse.Left, pos=start)
        QTest.mouseMove(self.widget, end, 30)
        QTest.mouseRelease(self.widget, QtMouse.Left, pos=end)
        for actual, expected in zip(created[0], [20, 20, 50, 50]):
            self.assertAlmostEqual(actual, expected, delta=1.0)

    def test_preview_refits_image_and_bbox_after_resize(self):
        before = self.widget._image_rect()
        self.widget.resize(600, 320)
        self.app.processEvents()
        after = self.widget._image_rect()
        self.assertGreater(after.width(), before.width())
        self.assertGreater(after.height(), before.height())
        box = self.widget._display_rect(self.widget._boxes[0])
        self.assertTrue(after.contains(box))

    def test_ai_box_is_painted_over_the_scaled_image(self):
        self.app.processEvents()
        rendered = self.widget.grab().toImage()
        rect = self.widget._display_rect(self.widget._boxes[0])
        pixel = rendered.pixelColor(round(rect.left()), round(rect.center().y()))
        expected = self.widget._detection_color(7)
        self.assertNotEqual(pixel.name(), "#ffffff")
        self.assertEqual(expected.alpha(), 255)

    def test_detection_colors_are_stable_across_reordering_and_distinct_by_id(self):
        boxes = [
            {"id": 7, "bbox_xyxy": [5, 5, 30, 30]},
            {"id": 8, "bbox_xyxy": [35, 5, 60, 30]},
            {"id": 9, "bbox_xyxy": [65, 5, 90, 30]},
        ]
        colors = {box["id"]: self.widget._detection_color(box["id"]).rgba()
                  for box in boxes}
        self.widget.set_boxes(list(reversed(boxes)))
        reordered = {box["id"]: self.widget._detection_color(box["id"]).rgba()
                     for box in self.widget._boxes}
        self.assertEqual(reordered, colors)
        self.assertEqual(len(set(colors.values())), len(boxes))

    def test_box_interiors_stay_transparent_and_unselected_outline_is_unchanged(self):
        boxes = [
            {"id": 7, "class_name": "face", "bbox_xyxy": [10, 10, 40, 40]},
            {"id": 8, "class_name": "body", "bbox_xyxy": [60, 10, 90, 40]},
        ]
        self.widget.set_boxes(boxes)
        self.app.processEvents()
        unselected_render = self.widget.grab().toImage()
        self.widget.select_box(7)
        self.app.processEvents()
        selected_render = self.widget.grab().toImage()

        first = self.widget._display_rect(boxes[0])
        second = self.widget._display_rect(boxes[1])
        first_center = unselected_render.pixelColor(round(first.center().x()), round(first.center().y()))
        second_center = selected_render.pixelColor(round(second.center().x()), round(second.center().y()))
        self.assertEqual(first_center.name(), "#ffffff")
        self.assertEqual(second_center.name(), "#ffffff")
        border_point = QPoint(round(second.left()), round(second.center().y()))
        self.assertEqual(unselected_render.pixelColor(border_point), selected_render.pixelColor(border_point))


class QtMouse:
    from PySide6.QtCore import Qt
    Left = Qt.MouseButton.LeftButton
