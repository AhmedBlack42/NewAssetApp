import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QListWidget, QListWidgetItem

from app.config import AppConfig
from app.gui.main_window import MainWindow
from app.core.clothing_taxonomy import clothing_classes, suggested_clothing_tags, validate_final_clothing_tag


class EmptyDatabase:
    def category_counts(self):
        return {}

    def count_sources(self):
        return 0

    def photoshoot_groups(self):
        return []

    def normal_crop_records(self, folder=None):
        return []

    def source_images(self, folder=None):
        return []

    def proposals_for_category(self, category):
        return []

    def proposals_for_source(self, source_id):
        return getattr(self, "source_proposals", [])

    def detections_for_source(self, source_id):
        return []

    def photoshoot_members(self, group_id):
        return []


class MainWindowLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow(AppConfig(), EmptyDatabase())
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_normal_review_card_contains_detection_suggestion_and_safe_actions(self):
        self.assertTrue(hasattr(self.window, "normal_review_card"))
        self.assertIn("Approve", self.window.normal_suggestion_approve.text())
        self.assertIn("Reject", self.window.normal_suggestion_reject.text())
        self.assertIn("Needs YOLO Correction", self.window.normal_needs_correction.text())
        self.assertIn("Crop Invalid", self.window.normal_mark_invalid.text())
        self.assertIn("Source Context", self.window.normal_source_context.text())

    def test_legacy_runtime_class_without_target_registry_match_disables_save(self):
        legacy_box = {
            "id": 77,
            "proposal_id": 77,
            "class_name": "location_outdoor",
            "bbox_xyxy": [10, 10, 200, 300],
        }
        self.window._populate_inspector_class_controls(legacy_box)
        self.app.processEvents()
        self.assertEqual(self.window.inspector_class_combo.currentData(), None)
        self.assertIn("legacy YOLO", self.window.inspector_class_combo.toolTip())
        self.assertFalse(self.window.inspector_class_button.isEnabled())

    def test_fullbody_normal_main_tags_have_no_duplicate_canonical_values(self):
        self.window.normal_assign_category.setCurrentIndex(
            self.window.normal_assign_category.findData("fullbody"))
        self.window._refresh_normal_taxonomy_options({})
        self.app.processEvents()
        values = [
            self.window.normal_body_tag.itemData(index)
            for index in range(self.window.normal_body_tag.count())
        ]
        populated = [value for value in values if value is not None]
        self.assertEqual(len(populated), len(set(populated)))

    def test_all_clothing_broad_families_validate_only_family_detailed_tags(self):
        for broad in clothing_classes():
            family = broad["class_name"]
            with self.subTest(family=family):
                allowed = suggested_clothing_tags(family)
                self.assertGreater(len(allowed), 0)
                for tag in allowed:
                    self.assertTrue(validate_final_clothing_tag(family, tag))
                for incompatible in set(
                        tag for other in clothing_classes()
                        if other["class_name"] != family
                        for tag in suggested_clothing_tags(other["class_name"])
                ) - set(allowed):
                    self.assertFalse(validate_final_clothing_tag(family, incompatible))

    def test_all_clothing_broad_families_populate_actual_gui_options(self):
        self.window.normal_assign_category.setCurrentIndex(
            self.window.normal_assign_category.findData("clothing"))
        self.app.processEvents()
        for broad in clothing_classes():
            family = broad["class_name"]
            with self.subTest(family=family):
                broad_index = self.window.normal_clothing_broad.findData(family)
                self.assertGreaterEqual(broad_index, 0)
                self.window.normal_clothing_broad.setCurrentIndex(broad_index)
                self.app.processEvents()
                actual = {
                    self.window.normal_body_tag.itemData(index)
                    for index in range(self.window.normal_body_tag.count())
                    if self.window.normal_body_tag.itemData(index) is not None
                }
                expected = set(suggested_clothing_tags(family))
                self.assertEqual(actual, expected)
                cover_options = {
                    self.window.normal_clothing_cover_area.itemData(index)
                    for index in range(self.window.normal_clothing_cover_area.count())
                    if self.window.normal_clothing_cover_area.itemData(index) is not None
                }
                from app.core.crop_rules import CLOTHING_FAMILY_AREAS
                self.assertEqual(
                    cover_options,
                    set(CLOTHING_FAMILY_AREAS.get(family, ())),
                )

    def test_clothing_broad_change_repopulates_only_family_detailed_tags(self):
        self.window.normal_assign_category.setCurrentIndex(
            self.window.normal_assign_category.findData("clothing"))
        self.app.processEvents()
        shirt = self.window.normal_clothing_broad.findData("shirt")
        self.window.normal_clothing_broad.setCurrentIndex(shirt)
        self.app.processEvents()
        shirt_tags = {
            self.window.normal_body_tag.itemData(i)
            for i in range(self.window.normal_body_tag.count())
        }
        self.assertIn("t_shirt", shirt_tags)
        self.assertNotIn("mini_skirt", shirt_tags)

        top = self.window.normal_clothing_broad.findData("top")
        self.window.normal_clothing_broad.setCurrentIndex(top)
        self.app.processEvents()
        top_tags = {
            self.window.normal_body_tag.itemData(i)
            for i in range(self.window.normal_body_tag.count())
        }
        self.assertIn("crop_top", top_tags)
        self.assertNotIn("t_shirt", top_tags)

    def test_category_change_clears_incompatible_saved_clothing_selection(self):
        row = {
            "id": 603,
            "category": "clothing",
            "normal_main_tag": "mini_skirt",
            "normal_clothing_broad_family": "skirt",
            "normal_clothing_cover_area": "ass_cover",
            "bbox_xyxy": [10, 10, 100, 100],
            "path": "",
        }
        self.window.normal_gallery.clear()
        item = QListWidgetItem("Clothing crop")
        item.setData(Qt.ItemDataRole.UserRole, row)
        self.window.normal_gallery.addItem(item)
        self.window.normal_gallery.setCurrentItem(item)
        self.app.processEvents()
        self.window.normal_assign_category.setCurrentIndex(
            self.window.normal_assign_category.findData("body_images"))
        self.app.processEvents()
        self.assertEqual(self.window.normal_assign_category.currentData(), "body_images")
        self.assertIsNone(self.window.normal_clothing_broad.currentData())
        self.assertIsNone(self.window.normal_clothing_cover_area.currentData())
        self.assertIsNone(self.window.normal_body_tag.currentData())

    def test_proposal_switch_clears_category_values_and_restores_saved_state(self):
        a = {
            "id": 601, "category": "clothing", "normal_main_tag": "mini_skirt",
            "normal_clothing_broad_family": "skirt", "normal_clothing_cover_area": "ass_cover",
            "bbox_xyxy": [10, 10, 100, 100], "path": "",
        }
        b = {
            "id": 602, "category": "body_images", "normal_main_tag": "boobs",
            "normal_subtags": ["cum"], "bbox_xyxy": [20, 20, 120, 120], "path": "",
        }
        self.window._render_normal_crop = lambda _row: (QPixmap(), "test crop")
        self.window.normal_gallery.clear()
        for row in (a, b):
            item = QListWidgetItem(str(row["id"]))
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.window.normal_gallery.addItem(item)

        self.window.normal_gallery.setCurrentRow(0)
        self.app.processEvents()
        self.assertEqual(
            self.window.normal_assign_category.currentData(),
            "clothing",
            f"drafts={self.window._normal_drafts}",
        )
        self.assertEqual(self.window.normal_clothing_broad.currentData(), "skirt")

        self.window.normal_gallery.setCurrentRow(1)
        self.app.processEvents()
        self.assertEqual(self.window.normal_assign_category.currentData(), "body_images")
        self.assertNotEqual(self.window.normal_clothing_broad.currentData(), "skirt")
        self.assertEqual(self.window.normal_body_tag.currentData(), "boobs")

        self.window.normal_gallery.setCurrentRow(0)
        self.app.processEvents()
        self.assertEqual(self.window.normal_assign_category.currentData(), "clothing")
        self.assertEqual(self.window.normal_clothing_broad.currentData(), "skirt")

    def test_uncategorized_normal_crop_requires_explicit_category(self):
        self.window.normal_assign_category.setCurrentIndex(
            self.window.normal_assign_category.findData(None))
        self.window.normal_gallery.clear()
        item = QListWidgetItem("Uncategorized crop")
        item.setData(Qt.ItemDataRole.UserRole, {"id": 501, "category": None})
        self.window.normal_gallery.addItem(item)
        self.window.normal_gallery.setCurrentItem(item)
        self.app.processEvents()
        self.window._normal_category_choice_changed(record_draft=False)
        self.app.processEvents()
        self.assertIsNone(self.window.normal_assign_category.currentData())
        self.assertFalse(self.window.normal_apply_category_button.isEnabled())

    def test_invalid_normal_category_enables_confirmation_without_callback_error(self):
        self.window._render_normal_crop = lambda _row: (QPixmap(), "test crop")
        self.window.normal_gallery.clear()
        item = QListWidgetItem("Invalid crop")
        item.setData(Qt.ItemDataRole.UserRole, {"id": 502, "category": None})
        self.window.normal_gallery.addItem(item)
        self.window.normal_gallery.setCurrentItem(item)
        self.window.normal_assign_category.setCurrentIndex(
            self.window.normal_assign_category.findData("invalid"))
        self.app.processEvents()
        self.assertEqual(self.window.normal_assign_category.currentData(), "invalid")
        self.assertEqual(self.window.normal_apply_category_button.text(), "Confirm invalid · Next")
        self.assertTrue(self.window.normal_apply_category_button.isEnabled())
        self.assertEqual(self.window._normal_drafts[502]["category"], "invalid")

    def test_scan_summary_counts_unchanged_sources_as_scanned(self):
        self.window._scan_completed({
            "indexed": 0,
            "total": 287,
            "new_or_changed": 0,
            "unchanged": 287,
            "duplicates": 0,
            "errors": [],
        })
        self.assertIn("Scanned 287 image(s)", self.window.progress.format())
        self.assertIn("0 new/changed · 287 unchanged", self.window.progress.format())

    def test_detection_selection_refreshes_person_inspector_from_database_fallback(self):
        person_box = {
            "id": 1126,
            "proposal_id": 1126,
            "source_image_id": 1,
            "class_name": "person",
            "original_class_name": "person",
            "confidence": 0.88,
            "bbox_xyxy": [10, 10, 200, 300],
            "original_bbox_xyxy": [10, 10, 200, 300],
            "status": "review_required",
            "classification_status": {},
            "category": "others",
        }
        location_box = {
            "id": 1125,
            "proposal_id": 1125,
            "source_image_id": 1,
            "class_name": "location_home",
            "original_class_name": "location_home",
            "confidence": 0.896,
            "bbox_xyxy": [0, 11, 908, 614],
            "original_bbox_xyxy": [0, 11, 908, 614],
            "status": "review_required",
            "classification_status": {},
            "category": "others",
        }
        self.window._active_source_id = 1
        self.window._all_detection_boxes = [location_box]
        self.window.database.detections_for_source = lambda _source_id: [location_box, person_box]
        self.window.preview.set_boxes([location_box, person_box])
        item = QListWidgetItem("Person")
        item.setData(Qt.ItemDataRole.UserRole, 1126)
        self.window.detection_list.addItem(item)
        self.window.detection_list.setCurrentItem(item)
        self.app.processEvents()
        self.assertIs(self.window.detection_list.currentItem(), item)
        selected_box = self.window.preview.selected_box()
        if selected_box is None:
            self.fail("Selecting a detection row did not select its preview box.")
        self.assertEqual(selected_box["id"], 1126)
        self.assertIn("Detection #1126", self.window.inspector_original.text())
        self.assertIn("person", self.window.inspector_original.text().casefold())

    def test_detection_selection_does_not_match_proposal_id_to_source_id(self):
        self.window.current_category = "sources"
        source_items = []
        self.window.gallery.blockSignals(True)
        for source_id in (1, 4):
            item = QListWidgetItem(f"Source {source_id}")
            item.setData(
                Qt.ItemDataRole.UserRole,
                {"id": source_id, "path": "", "width": 10, "height": 10,
                 "file_size": 0, "content_sha256": ""},
            )
            self.window.gallery.addItem(item)
            source_items.append(item)
        self.window.gallery.setCurrentItem(source_items[0])
        self.window.gallery.blockSignals(False)
        self.window._active_source_id = 1
        self.window._all_detection_boxes = [{
            "id": 4,
            "proposal_id": 4,
            "source_image_id": 1,
            "class_name": "face",
            "original_class_name": "face",
            "confidence": 0.75,
            "bbox_xyxy": [10, 10, 50, 50],
            "original_bbox_xyxy": [10, 10, 50, 50],
            "status": "review_required",
            "classification_status": {},
            "category": "body_images",
        }]
        detection_item = QListWidgetItem("Face #4")
        detection_item.setData(Qt.ItemDataRole.UserRole, 4)
        self.window.detection_list.addItem(detection_item)
        self.window.detection_list.setCurrentItem(detection_item)
        self.app.processEvents()
        self.assertIs(self.window.gallery.currentItem(), source_items[0])

    def test_normal_preview_form_and_navigation_stay_in_separate_regions(self):
        for width, height in ((900, 560), (1280, 800), (1360, 768), (1920, 1080)):
            with self.subTest(size=(width, height)):
                self.window.resize(width, height)
                self.app.processEvents()
                detail = self.window.normal_detail_panel
                preview_rect = self.window.normal_preview_panel.geometry()
                form_rect = self.window.normal_splitter.widget(2).geometry()
                self.assertGreaterEqual(preview_rect.height(), 100)
                self.assertGreaterEqual(form_rect.height(), 70)
                self.assertFalse(preview_rect.intersects(form_rect))
                self.assertEqual(self.window.normal_splitter.count(), 3)
                self.assertGreater(self.window.normal_splitter.widget(1).width(), 300)
                self.assertGreater(self.window.normal_splitter.widget(2).width(), 250)
                self.assertTrue(self.window.normal_previous_button.isVisible())
                self.assertTrue(self.window.normal_next_button.isVisible())
                for button in (self.window.normal_previous_button, self.window.normal_next_button):
                    top_left = button.mapTo(detail, QPoint(0, 0))
                    self.assertTrue(detail.rect().contains(QRect(top_left, button.size())))
                self.assertTrue(self.window.normal_export_button.isVisible())

    def test_normal_confirmation_and_separate_scroll_selectors(self):
        self.window.normal_assign_category.setCurrentIndex(
            self.window.normal_assign_category.findData("clothing"))
        self.app.processEvents()
        self.assertEqual(self.window.normal_apply_category_button.text(), "Confirm classification & Next")
        self.assertTrue(self.window.normal_clothing_broad_row.isVisible())
        self.assertIsInstance(self.window.normal_location, QListWidget)
        self.assertEqual(self.window.normal_location.selectionMode().name, "SingleSelection")
        self.assertLessEqual(self.window.normal_location.maximumHeight(), 80)
        self.assertEqual(self.window.normal_subtags.selectionMode().name, "MultiSelection")
        self.assertEqual(self.window.normal_corruption_states.selectionMode().name, "MultiSelection")
        self.window._refresh_normal_taxonomy_options({})
        self.assertFalse(any(self.window.normal_subtags.item(i).flags() & Qt.ItemFlag.ItemIsUserCheckable
                             for i in range(self.window.normal_subtags.count())))
        corruption = [self.window.normal_corruption_states.item(i)
                      for i in range(self.window.normal_corruption_states.count())]
        self.assertEqual([item.data(Qt.ItemDataRole.UserRole) for item in corruption],
                         ["slut", "whore", "u_whore", "conservative"])
        self.assertEqual(corruption[2].text(), "Ultimate Whore")
        self.assertFalse(any(item.flags() & Qt.ItemFlag.ItemIsUserCheckable
                             for item in corruption))
        self.window.normal_assign_category.setCurrentIndex(
            self.window.normal_assign_category.findData("body_images"))
        self.app.processEvents()
        self.assertFalse(self.window.normal_clothing_broad_row.isVisible())
        self.assertFalse(self.window.normal_corruption_states.isVisible())

    def test_bbox_edit_refreshes_normal_crop_geometry(self):
        original_bbox = [10, 10, 40, 40]
        corrected_bbox = [10, 10, 52, 55]
        proposal = {
            "id": 31,
            "detection_id": 31,
            "source_image_id": 3,
            "category": "clothing",
            "path": __file__,
            "bbox_xyxy": list(original_bbox),
            "normal_confirmed": False,
        }
        detection = {
            "id": 31,
            "proposal_id": 31,
            "source_image_id": 3,
            "class_name": "boobs_cover_item",
            "original_class_name": "boobs_cover_item",
            "confidence": 0.34,
            "bbox_xyxy": list(original_bbox),
            "original_bbox_xyxy": list(original_bbox),
            "status": "review_required",
            "classification_status": {},
            "category": "clothing",
        }
        self.window.database.normal_crop_records = lambda folder=None: [dict(proposal)]
        self.window.database.save_bbox_edit = lambda _detection_id, bbox: proposal.update(
            {"bbox_xyxy": list(bbox)})
        self.window.database.detections_for_source = lambda _source_id: [
            dict(detection, bbox_xyxy=list(proposal["bbox_xyxy"]))
        ]
        self.window._render_normal_crop = lambda _row: (QPixmap(), "test crop")
        self.window._active_source_id = 3
        self.window.current_category = "sources"
        self.window._all_detection_boxes = [detection]
        self.window.preview.set_boxes([detection])

        item = QListWidgetItem("Clothing crop")
        item.setData(Qt.ItemDataRole.UserRole, dict(proposal))
        self.window.normal_gallery.addItem(item)
        self.window.normal_gallery.setCurrentItem(item)
        self.app.processEvents()

        self.window._bbox_changed(31, corrected_bbox)
        self.app.processEvents()

        refreshed_item = next(
            self.window.normal_gallery.item(index)
            for index in range(self.window.normal_gallery.count())
            if (self.window.normal_gallery.item(index).data(Qt.ItemDataRole.UserRole)
                and self.window.normal_gallery.item(index).data(Qt.ItemDataRole.UserRole)["id"] == 31)
        )
        self.assertEqual(
            refreshed_item.data(Qt.ItemDataRole.UserRole)["bbox_xyxy"],
            corrected_bbox,
        )
        self.assertEqual(
            self.window.normal_gallery.currentItem().data(Qt.ItemDataRole.UserRole)["id"],
            31,
        )

    def test_thumbnail_cache_is_bounded_and_bbox_key_is_revision_sensitive(self):
        original_key = (31, "sha-a", (10.0, 10.0, 40.0, 40.0), "shirt", "boobs_cover")
        corrected_key = (31, "sha-a", (10.0, 10.0, 52.0, 55.0), "shirt", "boobs_cover")
        self.assertNotEqual(original_key, corrected_key)
        for index in range(140):
            key = (1000 + index, "sha", (index, 0, index + 10, 10), "shirt", "boobs_cover")
            self.window._normal_gallery_crop_cache[key] = QPixmap(1, 1)
            while len(self.window._normal_gallery_crop_cache) > self.window._normal_gallery_crop_cache_limit:
                self.window._normal_gallery_crop_cache.popitem(last=False)
        self.assertEqual(len(self.window._normal_gallery_crop_cache),
                         self.window._normal_gallery_crop_cache_limit)
        stats = self.window._normal_cache_stats
        self.assertEqual(stats["thumbnail_hits"] >= 0, True)
        self.assertEqual(stats["thumbnail_misses"] >= 0, True)
        self.assertEqual(stats["preview_hits"] >= 0, True)
        self.assertEqual(stats["preview_misses"] >= 0, True)

    def test_stale_thumbnail_result_is_discarded_after_gallery_refresh(self):
        old_key = (77, "sha", (1.0, 1.0, 10.0, 10.0), "shirt", "boobs_cover")
        corrected_key = (77, "sha", (2.0, 2.0, 12.0, 12.0), "shirt", "boobs_cover")
        self.window._normal_gallery_crop_cache[old_key] = QPixmap(10, 10)
        self.window._normal_gallery_crop_cache.pop(old_key, None)
        self.assertNotIn(old_key, self.window._normal_gallery_crop_cache)
        self.assertNotEqual(old_key, corrected_key)

    def test_scroll_resize_and_gallery_refresh_schedule_visible_thumbnail_loading(self):
        for index in range(250):
            item = QListWidgetItem(f"Proposal {index}")
            item.setData(Qt.ItemDataRole.UserRole, {
                "id": index + 1,
                "path": __file__,
                "bbox_xyxy": [1, 1, 20, 20],
                "content_sha256": f"sha-{index}",
            })
            self.window.normal_gallery.addItem(item)
        self.app.processEvents()
        self.window.resize(1280, 720)
        self.app.processEvents()
        scrollbar = self.window.normal_gallery.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.app.processEvents()
        self.window._schedule_visible_normal_thumbnails()
        self.app.processEvents()
        self.assertTrue(self.window._normal_thumbnail_debounce.isActive())
        self.window.normal_gallery.setCurrentRow(max(0, self.window.normal_gallery.count() - 1))
        self.app.processEvents()
        self.assertEqual(
            self.window.normal_gallery.currentRow(),
            self.window.normal_gallery.count() - 1,
        )

    def test_normal_shared_targets_fit_narrow_classification_panel(self):
        self.window.resize(1360, 768)
        self.window.normal_assign_category.setCurrentIndex(
            self.window.normal_assign_category.findData("body_images"))
        self.app.processEvents()
        shared = self.window.normal_shared_target_row
        for control in (
            self.window.normal_arousal_target_label,
            self.window.normal_arousal_target,
            self.window.normal_corruption_target_label,
            self.window.normal_corruption_target,
        ):
            top_left = control.mapTo(shared, QPoint(0, 0))
            self.assertTrue(shared.rect().contains(QRect(top_left, control.size())))
        self.assertEqual(
            self.window.normal_arousal_target.x(),
            self.window.normal_corruption_target.x(),
        )

    def test_professional_workstation_has_canvas_navigator_and_detection_inspector(self):
        for width, height in ((1280, 720), (1366, 768), (1920, 1080)):
            with self.subTest(size=(width, height)):
                self.window.resize(width, height)
                self.window.workspace_tabs.setCurrentIndex(1)
                self.app.processEvents()
                canvas = self.window.professional_splitter.widget(2)
                inspector = self.window.professional_splitter.widget(3)
                self.assertGreater(canvas.width(), inspector.width())
                self.assertGreaterEqual(inspector.width(), 300)
                self.assertTrue(self.window.inspector_tabs.tabBar().isVisible())
        self.window._all_detection_boxes = [
            {"id": 21, "category": "body_images", "class_name": "face",
             "original_class_name": "face", "confidence": 0.91,
             "status": "unreviewed", "bbox_xyxy": [10, 20, 100, 200],
             "classification_status": {}},
            {"id": 22, "category": "others", "class_name": "location_home",
             "original_class_name": "location_home", "confidence": 0.88,
             "status": "confirmed", "bbox_xyxy": [120, 20, 200, 200],
             "classification_status": {}},
        ]
        self.window._refresh_professional_detection_view()
        self.app.processEvents()
        self.assertEqual(self.window.professional_splitter.count(), 4)
        self.assertGreater(self.window.professional_splitter.widget(2).width(), 300)
        self.assertGreater(self.window.professional_splitter.widget(3).width(), 200)
        self.assertEqual(self.window.inspector_tabs.count(), 1)
        self.assertEqual(self.window.inspector_tabs.tabText(0), "Detection")
        self.assertFalse(hasattr(self.window, "inspector_tasks"))
        self.assertFalse(hasattr(self.window, "inspector_tags"))
        self.assertFalse(hasattr(self.window, "review_button"))
        filter_labels = [
            self.window.detection_filter.itemText(index)
            for index in range(self.window.detection_filter.count())
        ]
        self.assertNotIn("Body Images", filter_labels)
        self.assertNotIn("Clothing", filter_labels)
        self.window.detection_list.setCurrentRow(0)
        self.app.processEvents()
        first = self.window.detection_list.currentItem()
        if first is None:
            self.fail("The first detection was not selected.")
        self.assertEqual(first.data(Qt.ItemDataRole.UserRole), 21)
        selected_box = self.window.preview.selected_box()
        if selected_box is None:
            self.fail("The first detection row did not select its preview box.")
        self.assertEqual(selected_box["id"], 21)
        self.assertNotIn("CNN", first.text())
        self.assertNotIn("task labels", first.toolTip().casefold())
        self.window.detection_list.setCurrentRow(1)
        self.app.processEvents()
        selected_box = self.window.preview.selected_box()
        if selected_box is None:
            self.fail("The second detection row did not select its preview box.")
        self.assertEqual(selected_box["id"], 22)
        self.assertIn("Detection #22", self.window.inspector_original.text())

    def test_compact_header_and_professional_canvas_use_available_height(self):
        root = self.window.centralWidget()
        self.assertFalse(self.window.findChildren(QLabel, "PageTitle"))
        self.assertLessEqual(self.window.folder_edit.maximumHeight(), 32)
        for control in (self.window.folder_edit, self.window.browse_button, self.window.scan_button,
                        self.window.analyze_button, self.window.full_rescan_check):
            self.assertTrue(control.isVisible())
            top_left = control.mapTo(root, QPoint(0, 0))
            self.assertTrue(root.rect().contains(QRect(top_left, control.size())))

        self.window.current_category = "body_images"
        self.window._refresh_gallery()
        self.window.resize(1366, 768)
        self.window.workspace_tabs.setCurrentIndex(1)
        self.app.processEvents()
        canvas_height = self.window.preview.height()
        self.assertTrue(self.window.detection_list.isVisible())
        for button in (self.window.add_box_button, self.window.reject_box_button,
                       self.window.approve_bbox_button):
            self.assertTrue(button.isVisible())
            top_left = button.mapTo(self.window.detail_frame, QPoint(0, 0))
            self.assertTrue(self.window.detail_frame.rect().contains(QRect(top_left, button.size())))

        self.window.resize(1366, 900)
        self.app.processEvents()
        self.assertGreater(self.window.preview.height(), canvas_height)

    def test_professional_review_keeps_same_image_and_remaining_boxes_after_category_change(self):
        rows = [
            {"id": 10, "source_image_id": 7, "category": "clothing", "review_status": "confirmed",
             "path": __file__, "width": 100, "height": 80},
            {"id": 11, "source_image_id": 7, "category": "body_images", "review_status": "review_required",
             "path": __file__, "width": 100, "height": 80},
        ]
        self.window.database.source_proposals = rows
        self.window.current_category = "body_images"
        self.window._professional_keep_source_id = 7
        self.window._professional_keep_proposal_id = 10
        self.window.gallery.blockSignals(True)
        self.window._refresh_gallery()
        self.window.gallery.blockSignals(False)
        proposal_ids = {self.window.gallery.item(i).data(Qt.ItemDataRole.UserRole)["id"]
                        for i in range(self.window.gallery.count())
                        if isinstance(self.window.gallery.item(i).data(Qt.ItemDataRole.UserRole), dict)}
        self.assertEqual(proposal_ids, {10, 11})
        selected = self.window.gallery.currentItem().data(Qt.ItemDataRole.UserRole)
        self.assertEqual(selected["id"], 10)


if __name__ == "__main__":
    unittest.main()
