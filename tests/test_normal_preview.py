import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from app.gui.main_window import AspectRatioPreview


class AspectRatioPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_image_fits_and_keeps_aspect_ratio_after_resize(self):
        preview = AspectRatioPreview()
        preview.set_source_pixmap(QPixmap(800, 400))
        preview.show()
        try:
            for width, height in ((320, 160), (600, 180), (240, 300)):
                preview.resize(width, height)
                self.app.processEvents()
                fitted = preview.pixmap()
                bounds = preview.contentsRect().size()
                self.assertFalse(fitted.isNull())
                self.assertLessEqual(fitted.width(), bounds.width())
                self.assertLessEqual(fitted.height(), bounds.height())
                self.assertAlmostEqual(fitted.width() / fitted.height(), 2.0, places=2)
        finally:
            preview.close()

    def test_resize_refits_original_source_instead_of_rescaling_prior_fit(self):
        preview = AspectRatioPreview()
        source = QPixmap(1000, 500)
        source.fill(QColor("#42d392"))
        preview.set_source_pixmap(source)
        preview.show()
        try:
            preview.resize(120, 80)
            self.app.processEvents()
            small = preview.pixmap().size()
            preview.resize(500, 300)
            self.app.processEvents()
            large = preview.pixmap().size()
            self.assertGreater(large.width(), small.width())
            self.assertLessEqual(large.width(), preview.contentsRect().width())
            self.assertEqual(preview._source_pixmap.size(), source.size())
        finally:
            preview.close()


if __name__ == "__main__":
    unittest.main()
