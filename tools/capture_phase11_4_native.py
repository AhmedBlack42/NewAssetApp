"""Capture NewAssetApp's real Qt window using disposable synthetic records."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "gui_screenshots" / "phase11_4"
FIXTURE = OUTPUT / "disposable_test_data"
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.core.database import Database
from app.gui.correction_dialog import CorrectionDialog
from app.gui.main_window import MainWindow


class CaptureConfig:
    app_name = "NewAssetApp · Phase 11.4 disposable review"
    data_dir = ROOT / "data"

    @property
    def output_dir(self):
        return FIXTURE / "outputs"

    @property
    def logs_dir(self):
        return FIXTURE / "logs"

    @property
    def database_path(self):
        return FIXTURE / "newassetapp-disposable-v11.sqlite3"


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


class RGBQUAD(ctypes.Structure):
    _fields_ = [("rgbBlue", ctypes.c_ubyte), ("rgbGreen", ctypes.c_ubyte),
                ("rgbRed", ctypes.c_ubyte), ("rgbReserved", ctypes.c_ubyte)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD * 1)]


def _win32_capture(window, filename: Path) -> tuple[int, int]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = ctypes.c_int
    user32.GetWindowDC.argtypes = [ctypes.c_void_p]
    user32.GetWindowDC.restype = ctypes.c_void_p
    user32.PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    user32.PrintWindow.restype = ctypes.c_int
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                                ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), ctypes.c_uint]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    hwnd = int(window.winId())
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    width, height = rect.right - rect.left, rect.bottom - rect.top
    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, 2):
            raise RuntimeError("Win32 PrintWindow could not capture the NewAssetApp window.")
        info = BITMAPINFO()
        info.bmiHeader = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height,
                                          1, 32, 0, width * height * 4, 0, 0, 0, 0)
        buffer = (ctypes.c_ubyte * (width * height * 4))()
        rows = gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer,
                               ctypes.byref(info), 0)
        if rows != height:
            raise RuntimeError(f"Win32 PrintWindow returned only {rows} of {height} rows.")
        image = Image.frombuffer("RGBA", (width, height), bytes(buffer), "raw", "BGRA", 0, 1)
        image.convert("RGB").save(filename, "PNG")
        image.close()
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)
    return width, height


def _capture_desktop(filename: Path) -> tuple[int, int]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetDC.argtypes = [ctypes.c_void_p]
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    gdi32.BitBlt.restype = ctypes.c_int
    gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                                ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), ctypes.c_uint]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    screen_width, screen_height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    screen_dc = user32.GetDC(None)
    memory_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, screen_width, screen_height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not gdi32.BitBlt(memory_dc, 0, 0, screen_width, screen_height,
                            screen_dc, 0, 0, 0x00CC0020):
            raise RuntimeError("Win32 BitBlt could not capture the desktop.")
        info = BITMAPINFO()
        info.bmiHeader = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), screen_width,
                                          -screen_height, 1, 32, 0,
                                          screen_width * screen_height * 4, 0, 0, 0, 0)
        buffer = (ctypes.c_ubyte * (screen_width * screen_height * 4))()
        rows = gdi32.GetDIBits(memory_dc, bitmap, 0, screen_height, buffer,
                               ctypes.byref(info), 0)
        if rows != screen_height:
            raise RuntimeError(f"Win32 BitBlt returned only {rows} of {screen_height} rows.")
        image = Image.frombuffer("RGBA", (screen_width, screen_height), bytes(buffer), "raw", "BGRA", 0, 1)
        image.convert("RGB").save(filename, "PNG")
        image.close()
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, screen_dc)
    return screen_width, screen_height


def _synthetic_source(db: Database, name: str, *, mode: str, size: tuple[int, int],
                      boxes: list[tuple[int, str, list[int], str]]) -> tuple[int, Path, list[int]]:
    path = FIXTURE / "images" / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new(mode, size, (0, 0, 0, 0) if mode == "RGBA" else (32, 40, 52))
    draw = ImageDraw.Draw(image)
    if mode == "RGBA":
        draw.ellipse((size[0] * .25, size[1] * .08, size[0] * .75, size[1] * .94),
                     fill=(210, 132, 168, 255))
        draw.rectangle((size[0] * .34, size[1] * .26, size[0] * .66, size[1] * .78),
                       fill=(98, 143, 198, 255))
    else:
        draw.rounded_rectangle((size[0] * .20, size[1] * .17, size[0] * .80, size[1] * .85),
                               radius=26, fill=(178, 116, 82))
    image.save(path)
    image.close()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    source_id, _ = db.upsert_source_image({
        "path": str(path.resolve()), "sha256": digest, "width": size[0], "height": size[1],
        "file_size": path.stat().st_size, "modified_ns": path.stat().st_mtime_ns,
    })
    proposal_ids = []
    for class_id, class_name, bbox, category in boxes:
        result = db.record_yolo_detection(
            source_id, model_id="legacy_yolo", model_digest="disposable-fixture",
            class_id=class_id, class_name=class_name, confidence=.91, bbox_xyxy=bbox)
        proposal_id = int(result["proposal_id"])
        with db.connect() as connection:
            connection.execute("UPDATE asset_proposals SET category=?,asset_type=? WHERE id=?",
                               (category, "clothed" if category == "fullbody" else category, proposal_id))
        proposal_ids.append(proposal_id)
    return source_id, path, proposal_ids


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    FIXTURE.mkdir(parents=True, exist_ok=True)
    config = CaptureConfig()
    db = Database(config.database_path)
    db.initialize()
    fullbody_id, _fullbody_path, fullbody_props = _synthetic_source(
        db, "synthetic_fullbody", mode="RGBA", size=(900, 1400),
        boxes=[(13, "fullbody_maid", [100, 70, 800, 1340], "fullbody")])
    body_id, _body_path, body_props = _synthetic_source(
        db, "synthetic_portrait", mode="RGBA", size=(900, 900),
        boxes=[(1, "face", [180, 130, 720, 670], "body_images")])
    clothing_id, _clothing_path, clothing_props = _synthetic_source(
        db, "synthetic_clothing", mode="RGB", size=(900, 700),
        boxes=[(8, "boobs_cover_item", [150, 90, 760, 640], "clothing")])
    review_id, _review_path, review_props = _synthetic_source(
        db, "synthetic_overlapping_review", mode="RGB", size=(1200, 900),
        boxes=[(1, "face", [300, 100, 830, 700], "body_images"),
               (3, "boobs", [410, 210, 900, 670], "body_images"),
               (8, "boobs_cover_item", [470, 330, 970, 830], "clothing")])
    db.save_normal_crop_choice(fullbody_props[0], "fullbody", main_tag="clothed",
                               fullbody_state="clothed")
    db.save_normal_crop_choice(body_props[0], "body_images", "portrait", main_tag="portrait",
                               location="home")
    db.save_normal_crop_choice(clothing_props[0], "clothing", main_tag="heels",
                               clothing_broad_family="footwear")

    app = QApplication.instance() or QApplication([])
    app.setApplicationName(config.app_name)
    window = MainWindow(config, db)
    window.resize(1360, 768)
    window.show()
    app.processEvents()
    sizes = []

    def capture(name: str):
        app.processEvents()
        width, height = _win32_capture(window, OUTPUT / f"{name}_{window.width()}x{window.height()}.png")
        sizes.append({"file": f"{name}_{window.width()}x{window.height()}.png",
                      "width": width, "height": height})

    for category, proposal_id, name in (
        ("fullbody", fullbody_props[0], "normal_fullbody"),
        ("body_images", body_props[0], "normal_body_images_portrait"),
        ("clothing", clothing_props[0], "normal_clothing"),
    ):
        window.workspace_tabs.setCurrentIndex(0)
        window.normal_category_filter.setCurrentIndex(window.normal_category_filter.findData(category))
        app.processEvents()
        for index in range(window.normal_gallery.count()):
            item = window.normal_gallery.item(index)
            row = item.data(Qt.ItemDataRole.UserRole)
            if row and int(row["id"]) == proposal_id:
                window.normal_gallery.setCurrentItem(item)
                break
        capture(name)
    body_filter = window.normal_category_filter.findData("body_images")
    window.normal_category_filter.setCurrentIndex(body_filter)
    for index in range(window.normal_gallery.count()):
        item = window.normal_gallery.item(index)
        row = item.data(Qt.ItemDataRole.UserRole)
        if row and int(row["id"]) == body_props[0]:
            window.normal_gallery.setCurrentItem(item)
            break
    scroll_area = window.normal_detail_splitter.widget(1)
    scroll_area.verticalScrollBar().setValue(scroll_area.verticalScrollBar().maximum())
    app.processEvents()
    popup_width, popup_height = _win32_capture(window, OUTPUT / "normal_location_scroll_list.png")
    sizes.append({"file": "normal_location_scroll_list.png",
                  "width": popup_width, "height": popup_height})
    capture("normal_location_and_corruption_scroll")

    window.workspace_tabs.setCurrentIndex(1)
    app.processEvents()
    for index in range(window.gallery.count()):
        item = window.gallery.item(index)
        row = item.data(Qt.ItemDataRole.UserRole)
        if row and int(row.get("id", -1)) == review_id:
            window.gallery.setCurrentItem(item)
            break
    app.processEvents()
    capture("professional_overlapping_detections")
    window.detection_list.setCurrentRow(0)
    app.processEvents()
    capture("professional_selected_detection_editable_box")
    window.box_visibility_mode.setCurrentIndex(window.box_visibility_mode.findData("hidden"))
    capture("professional_source_boxes_hidden")
    window.box_visibility_mode.setCurrentIndex(window.box_visibility_mode.findData("all"))

    review_rows = db.proposals_for_category("body_images")
    if review_rows:
        proposal = dict(review_rows[0])
        proposal["review_history"] = db.proposal_review_history(int(proposal["id"]))
        dialog = CorrectionDialog(proposal, window.tag_library, window)
        dialog.show()
        app.processEvents()
        width, height = _win32_capture(dialog, OUTPUT / "professional_separate_cnn_controls.png")
        sizes.append({"file": "professional_separate_cnn_controls.png", "width": width, "height": height})
        dialog.close()
    for tab, tab_name in ((0, "normal"), (1, "professional")):
        window.workspace_tabs.setCurrentIndex(tab)
        for width, height in ((900, 560), (1280, 800), (1360, 768)):
            window.resize(width, height)
            if tab == 0:
                window.normal_detail_splitter.widget(1).verticalScrollBar().setValue(0)
            app.processEvents()
            capture(f"{tab_name}_window_size_{width}x{height}")
    window.close()
    app.processEvents()
    (OUTPUT / "capture_manifest.json").write_text(json.dumps({
        "capture_method": "Win32 PrintWindow from real NewAssetApp Qt windows",
        "database": str(config.database_path),
        "synthetic_data_only": True,
        "window_sizes": sizes,
        "display": {"width": ctypes.windll.user32.GetSystemMetrics(0),
                    "height": ctypes.windll.user32.GetSystemMetrics(1)},
        "source_ids": [fullbody_id, body_id, clothing_id, review_id],
        "overlap_proposal_ids": review_props,
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
