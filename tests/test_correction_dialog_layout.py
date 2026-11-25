import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from app.core.tag_library import TagLibrary
from app.gui.correction_dialog import CorrectionDialog


class CorrectionDialogLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.tag_library = TagLibrary(Path(__file__).resolve().parents[1] / "data" / "tags")

    def test_action_buttons_remain_visible_at_compact_dialog_size(self):
        proposal = {
            "id": 1,
            "category": "body_images",
            "latest_correction_json": None,
            "yolo_class_name": "bodypart_face",
            "yolo_confidence": 0.9,
            "cnn_class_name": "bodypart_face",
            "cnn_confidence": 0.9,
            "content_sha256": "fixture",
            "review_history": [],
            "detection_id": 1,
            "width": 900,
            "height": 900,
            "yolo_x1": 100,
            "yolo_y1": 100,
            "yolo_x2": 800,
            "yolo_y2": 800,
        }
        dialog = CorrectionDialog(proposal, self.tag_library)
        try:
            for width, height in ((560, 500), (760, 700)):
                with self.subTest(size=(width, height)):
                    dialog.resize(width, height)
                    dialog.show()
                    self.app.processEvents()
                    buttons = (dialog.save_class_button, dialog.save_bbox_button,
                               dialog.save_combined_button, dialog.cancel_button)
                    rects = []
                    for button in buttons:
                        self.assertTrue(button.isVisible())
                        top_left = button.mapTo(dialog, QPoint(0, 0))
                        rect = QRect(top_left, button.size())
                        self.assertTrue(dialog.rect().contains(rect))
                        rects.append(rect)
                    self.assertFalse(rects[0].intersects(rects[1]))
                    self.assertFalse(rects[2].intersects(rects[3]))
                    self.assertTrue(dialog.save_class_button.isEnabled()
                                    or dialog.save_bbox_button.isEnabled()
                                    or dialog.save_combined_button.isEnabled())
                    self.assertTrue(dialog.confirm_button.isHidden())
                    self.assertTrue(dialog.save_button.isHidden())
                    self.assertTrue(dialog.reject_button.isHidden())
        finally:
            dialog.close()

    def test_form_and_task_controls_fit_without_horizontal_scrolling(self):
        proposal = {
            "id": 11,
            "category": "fullbody",
            "latest_correction_json": None,
            "yolo_class_name": "fullbody_bottomless",
            "yolo_confidence": 0.9,
            "content_sha256": "fixture",
            "review_history": [],
            "detection_id": 11,
            "width": 900,
            "height": 900,
            "yolo_x1": 100,
            "yolo_y1": 100,
            "yolo_x2": 800,
            "yolo_y2": 800,
        }
        dialog = CorrectionDialog(proposal, self.tag_library)
        try:
            scroll = dialog.findChild(QScrollArea)
            self.assertIsNotNone(scroll)
            for width, height in ((560, 500), (760, 700)):
                with self.subTest(size=(width, height)):
                    dialog.resize(width, height)
                    dialog.show()
                    self.app.processEvents()
                    self.assertFalse(scroll.horizontalScrollBar().isVisible())
                    self.assertFalse(dialog.yolo_class.isHidden())
                    self.assertFalse(dialog.save_class_button.isHidden())
                    self.assertFalse(dialog.save_bbox_button.isHidden())
                    self.assertFalse(dialog.save_combined_button.isHidden())
                    self.assertTrue(all(panel.isHidden() for panel in dialog.task_panels.values()))
                    self.assertTrue(dialog.confirm_button.isHidden())
                    self.assertTrue(dialog.save_button.isHidden())
        finally:
            dialog.close()

    def test_class_and_bbox_correction_actions_are_separate(self):
        proposal = {
            "id": 10, "category": "body_images", "latest_correction_json": None,
            "yolo_class_id": 1, "yolo_class_name": "face", "yolo_confidence": .9,
            "content_sha256": "fixture", "review_history": [], "detection_id": 10,
            "width": 500, "height": 400, "yolo_x1": 10, "yolo_y1": 20,
            "yolo_x2": 450, "yolo_y2": 380,
        }
        class_dialog = CorrectionDialog(proposal, self.tag_library)
        try:
            class_dialog.yolo_class.setCurrentIndex(class_dialog.yolo_class.findData(0))
            class_dialog._submit_class_correction()
            self.assertEqual(class_dialog.decision_type, "class_correction")
            self.assertEqual(class_dialog.result_payload(), {
                "yolo_annotation_registry_id": "newassetapp_yolo_detector_v1",
                "yolo_annotation_class_id": 0,
                "yolo_annotation_class_name": "person",
            })
        finally:
            class_dialog.close()

        bbox_dialog = CorrectionDialog(proposal, self.tag_library)
        try:
            bbox_dialog.boxes[0].setValue(15)
            bbox_dialog._submit_bbox_correction()
            self.assertEqual(bbox_dialog.decision_type, "bbox_correction")
            self.assertEqual(bbox_dialog.result_payload()["bbox_xyxy"],
                             [15.0, 20.0, 450.0, 380.0])
        finally:
            bbox_dialog.close()

    def test_correction_dialog_has_no_duplicate_yolo_editor_actions(self):
        proposal = {
            "id": 2, "category": "body_images", "latest_correction_json": None,
            "yolo_class_id": 1, "yolo_class_name": "face", "yolo_confidence": .88,
            "content_sha256": "fixture", "review_history": [], "detection_id": 2,
            "width": 500, "height": 500, "yolo_x1": 10, "yolo_y1": 10,
            "yolo_x2": 400, "yolo_y2": 400,
        }
        dialog = CorrectionDialog(proposal, self.tag_library)
        try:
            self.assertFalse(dialog.yolo_class.isHidden())
            self.assertFalse(dialog.save_class_button.isHidden())
            self.assertFalse(dialog.save_bbox_button.isHidden())
            self.assertFalse(dialog.save_combined_button.isHidden())
            self.assertTrue(dialog.confirm_button.isHidden())
            self.assertTrue(dialog.save_button.isHidden())
            self.assertTrue(all(panel.isHidden() for panel in dialog.task_panels.values()))
        finally:
            dialog.close()

    def test_manual_or_orphan_proposal_cannot_submit_detection_task_actions(self):
        proposal = {
            "id": 30, "category": "others", "latest_correction_json": None,
            "yolo_class_id": None, "yolo_class_name": None, "yolo_confidence": None,
            "content_sha256": "fixture", "review_history": [], "detection_id": None,
            "width": 900, "height": 900,
        }
        dialog = CorrectionDialog(proposal, self.tag_library)
        try:
            with patch("app.gui.correction_dialog.QMessageBox.warning"):
                dialog._submit_task_action("corruption", "confirmed")
            self.assertIsNone(dialog.decision_type if dialog.decision_type == "task_classification" else None)
            self.assertIn("no linked Detection", dialog.task_error_labels["corruption"].text())
            with patch("app.gui.correction_dialog.QMessageBox.warning"):
                dialog._submit_class_correction()
            self.assertNotEqual(dialog.decision_type, "class_correction")
        finally:
            dialog.close()

    def test_person_roi_uses_one_corruption_classifier_target_without_fullbody_label(self):
        proposal = {
            "id": 3, "category": "others", "latest_correction_json": None,
            "yolo_class_id": 0, "yolo_class_name": "person", "yolo_confidence": .9,
            "content_sha256": "fixture", "review_history": [], "detection_id": None,
            "width": 900, "height": 900, "yolo_x1": 80, "yolo_y1": 60,
            "yolo_x2": 820, "yolo_y2": 850,
        }
        dialog = CorrectionDialog(proposal, self.tag_library)
        try:
            target_index = dialog.corruption_cnn_target.findData("slut")
            self.assertGreater(target_index, 0)
            dialog.corruption_cnn_target.setCurrentIndex(target_index)
            payload = dialog.result_payload()
            self.assertEqual(payload["category"], "others")
            self.assertEqual(payload["corruption_classifier_target"], "slut")
            self.assertEqual(payload["corruption_state"], "slut")
            self.assertIsNone(payload.get("main_tag"))
            self.assertIsNone(payload.get("unified_cnn_class"))
            self.assertFalse(payload["corruption_training_eligible"])
            dialog._submit_task_action("corruption", "confirmed")
            self.assertEqual(dialog.decision_type, "task_classification")
            self.assertEqual(dialog._task_action["task_head"], "corruption")
            self.assertEqual(dialog.result_payload()["shared_cnn_training_tasks"], [])
        finally:
            dialog.close()

    def test_corruption_has_one_control_and_park_is_not_a_corruption_subtag(self):
        dialog = CorrectionDialog({
            "id": 9, "category": "fullbody", "latest_correction_json": None,
            "yolo_class_name": "fullbody", "yolo_confidence": .9,
            "content_sha256": "fixture", "review_history": [], "detection_id": 9,
            "width": 900, "height": 900, "yolo_x1": 10, "yolo_y1": 10,
            "yolo_x2": 890, "yolo_y2": 890,
        }, self.tag_library)
        try:
            corruption_combo_values = {
                dialog.corruption_cnn_target.itemText(i)
                for i in range(dialog.corruption_cnn_target.count())
            }
            self.assertIn("Ultimate Whore", corruption_combo_values)
            self.assertFalse(hasattr(dialog, "corruption_state"))
            subtag_values = {
                dialog.subtags.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(dialog.subtags.count())
            }
            self.assertNotIn("park", subtag_values)
            self.assertTrue(all("Conservative" not in text and "Slut" not in text
                               and "Whore" not in text for text in
                               [dialog.subtags.item(i).text()
                                for i in range(dialog.subtags.count())]))
        finally:
            dialog.close()

    def test_fullbody_head_exposes_all_five_states_and_person_hides_arousal(self):
        fullbody = CorrectionDialog({
            "id": 4, "category": "fullbody", "latest_correction_json": None,
            "yolo_class_id": 13, "yolo_class_name": "fullbody_maid", "yolo_confidence": .9,
            "content_sha256": "fixture", "review_history": [], "detection_id": 4,
            "width": 900, "height": 900, "yolo_x1": 10, "yolo_y1": 10,
            "yolo_x2": 890, "yolo_y2": 890,
        }, self.tag_library)
        try:
            self.assertTrue(fullbody.fullbody_cnn_target.isHidden())
            self.assertTrue(fullbody.task_panels["fullbody"].isHidden())
        finally:
            fullbody.close()

        person = CorrectionDialog({
            "id": 5, "category": "others", "latest_correction_json": None,
            "yolo_class_id": 0, "yolo_class_name": "person", "yolo_confidence": .9,
            "content_sha256": "fixture", "review_history": [], "detection_id": 5,
            "width": 900, "height": 900, "yolo_x1": 10, "yolo_y1": 10,
            "yolo_x2": 890, "yolo_y2": 890,
        }, self.tag_library)
        try:
            self.assertTrue(person.task_panels["arousal"].isHidden())
            self.assertTrue(person.task_panels["corruption"].isHidden())
        finally:
            person.close()

    def test_corruption_task_eligibility_uses_detection_class_not_proposal_category(self):
        cases = (
            (0, "person", "others"),
            (2, "portrait_frame", "body_images"),
            (20, "fullbody_clothed", "fullbody"),
        )
        for class_id, class_name, category in cases:
            with self.subTest(class_name=class_name):
                dialog = CorrectionDialog({
                    "id": class_id + 20, "category": category,
                    "latest_correction_json": None, "yolo_class_id": class_id,
                    "yolo_class_name": class_name, "yolo_confidence": .9,
                    "content_sha256": "fixture", "review_history": [],
                    "detection_id": class_id + 20, "width": 900, "height": 900,
                    "yolo_x1": 10, "yolo_y1": 10, "yolo_x2": 890, "yolo_y2": 890,
                }, self.tag_library)
                try:
                    self.assertTrue(dialog.task_panels["corruption"].isHidden())
                    self.assertFalse(dialog.result_payload()["corruption_training_eligible"])
                    dialog.validity_state.setCurrentIndex(
                        dialog.validity_state.findData("valid"))
                    target = dialog.corruption_cnn_target.findData("slut")
                    dialog.corruption_cnn_target.setCurrentIndex(target)
                    dialog.task_training_checks["corruption"].setChecked(True)
                    dialog._submit_task_action("corruption", "confirmed")
                    self.assertEqual(dialog._task_action["task_head"], "corruption")
                    self.assertTrue(dialog._task_action["training_eligible"])
                    self.assertFalse(dialog.result_payload()["corruption_training_eligible"])
                finally:
                    dialog.close()

    def test_location_selector_requires_location_group_assignment(self):
        proposal = {
            "id": 6, "category": "others", "latest_correction_json": None,
            "yolo_class_id": 0, "yolo_class_name": "person", "yolo_confidence": .9,
            "content_sha256": "fixture", "review_history": [], "detection_id": 6,
            "width": 900, "height": 900, "yolo_x1": 10, "yolo_y1": 10,
            "yolo_x2": 890, "yolo_y2": 890,
        }
        dialog = CorrectionDialog(proposal, self.tag_library)
        try:
            self.assertTrue(dialog.task_panels["location"].isHidden())
            location_index = dialog.yolo_class.findData(30)
            self.assertGreater(location_index, 0)
            dialog.yolo_class.setCurrentIndex(location_index)
            self.assertFalse(dialog.task_panels["location"].isHidden())
            for index in range(dialog.location_tag.count()):
                item = dialog.location_tag.item(index)
                if item.data(Qt.ItemDataRole.UserRole) == "beach":
                    item.setSelected(True)
                    break
            self.assertEqual(dialog.result_payload()["location_tag"], "beach")
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
